"""
The subconscious interceptor — Layer 2 (Business Constraints) + Layer 3 (System
Safety). This layer is immutable: neither the merchant nor Qwen can override it.

Two entry points, one ruleset:
  • Merchant pricing/promo mutations (Sprint 2)  -> enforce_price / enforce_discount
  • Qwen ProposedActions (Sprint 3)              -> validate_action / validate_decision

Both flow through the same enforce_* primitives so the floor is written once and
proven now, before any autonomy exists.

Layer 2 — Business Constraints (margin floor, discount ceiling, per-product min
          price)  -> auto-clamp with a warning the merchant sees.
Layer 3 — System Safety (price/discounted price below cost)  -> hard block.

Rewritten for the current schema (CLAUDE.md): the old brand-tweak / colour-
temperature code referenced fields that no longer exist. Brand-tweak warnings
are a frontend-local check against BrandGuardRules.allowed_color_palette with
zero round-trip — they do not belong here.
"""
from __future__ import annotations

from app.models.schemas import (
    ProposedAction,
    BusinessProfile,
    BusinessConstraints,
    ValidationResult,
    Violation,
    RiskLevel,
)
from app.services.pricing import margin_floor_price


# ─── Layer 2 / 3 primitives — used by both merchant routes and Qwen validation ─

def enforce_price(
    *,
    cost_price: float,
    proposed_price: float,
    constraints: BusinessConstraints,
    product_id: str = "",
) -> tuple[float, list[Violation]]:
    """Clamp a proposed price up to the margin floor; hard-block below cost.

    Returns (final_price, violations). If a `blocked` violation is present the
    caller MUST reject the change — the returned price is not safe to apply.
    """
    violations: list[Violation] = []

    # Layer 3 — system safety. Selling below cost is never allowed.
    if proposed_price < cost_price:
        violations.append(
            Violation(
                rule="below_cost",
                severity="blocked",
                message=(
                    f"${proposed_price:.2f} is below the ${cost_price:.2f} unit cost. "
                    "Selling at a loss is blocked."
                ),
                original_value=proposed_price,
                clamped_value=None,
            )
        )
        return proposed_price, violations

    # Layer 2 — margin floor (+ any per-product minimum the merchant set).
    floor = margin_floor_price(
        cost_price,
        constraints.min_profit_margin_percent,
        constraints.min_price.get(product_id, 0.0),
    )
    if proposed_price < floor:
        violations.append(
            Violation(
                rule="min_profit_margin",
                severity="warning",
                message=(
                    f"${proposed_price:.2f} breaks your {constraints.min_profit_margin_percent:g}% "
                    f"minimum margin. Clamped to ${floor:.2f}."
                ),
                original_value=proposed_price,
                clamped_value=floor,
            )
        )
        return floor, violations

    return round(proposed_price, 2), violations


def enforce_discount(
    *,
    cost_price: float,
    base_price: float,
    discount_percent: float,
    constraints: BusinessConstraints,
) -> tuple[float, list[Violation]]:
    """Clamp a discount to the ceiling; hard-block if it drives price below cost.

    Returns (final_discount_percent, violations). A `blocked` violation means the
    discount can't be applied at all (even clamped, it would sell below cost).
    """
    violations: list[Violation] = []
    d = discount_percent

    # Layer 2 — discount ceiling.
    if d > constraints.max_discount_percent:
        violations.append(
            Violation(
                rule="max_discount",
                severity="warning",
                message=(
                    f"{d:g}% exceeds your {constraints.max_discount_percent:g}% discount ceiling. "
                    f"Clamped to {constraints.max_discount_percent:g}%."
                ),
                original_value=d,
                clamped_value=constraints.max_discount_percent,
            )
        )
        d = constraints.max_discount_percent

    # Layer 3 — even the clamped discount must not sell below cost.
    discounted = base_price * (1 - d / 100)
    if discounted < cost_price:
        violations.append(
            Violation(
                rule="below_cost",
                severity="blocked",
                message=(
                    f"A {d:g}% discount drops the price to ${discounted:.2f}, "
                    f"below the ${cost_price:.2f} unit cost. Blocked."
                ),
                original_value=discount_percent,
                clamped_value=None,
            )
        )
        return d, violations

    return d, violations


def blocked(violations: list[Violation]) -> bool:
    return any(v.severity == "blocked" for v in violations)


# ─── Qwen ProposedAction validation (Sprint 3 reuse) ──────────────────────────

def _extract_product_id(path: str) -> str:
    # /products/prod_123/price -> prod_123
    parts = path.split("/")
    try:
        return parts[parts.index("products") + 1]
    except (ValueError, IndexError):
        return ""


def validate_action(action: ProposedAction, profile: BusinessProfile) -> ValidationResult:
    """Every Qwen-proposed action passes through here before reaching the
    merchant. Price and discount patches are run through the same Layer 2/3
    primitives the merchant routes use."""
    violations: list[Violation] = []
    clamped_patches = [p.model_copy(deep=True) for p in action.patch]

    product_map = {p.id: p for p in profile.products}
    constraints = profile.constraints

    for i, patch in enumerate(clamped_patches):
        if patch.op.value != "replace" or not isinstance(patch.value, (int, float)):
            continue

        if "/price" in patch.path:
            product = product_map.get(_extract_product_id(patch.path))
            if product:
                final, vs = enforce_price(
                    cost_price=product.cost_price,
                    proposed_price=float(patch.value),
                    constraints=constraints,
                    product_id=product.id,
                )
                violations.extend(vs)
                if not blocked(vs) and final != patch.value:
                    clamped_patches[i] = patch.model_copy(update={"value": final})

        elif "/discount_percent" in patch.path:
            # Discount patch without product context — enforce the ceiling only.
            if patch.value > constraints.max_discount_percent:
                violations.append(
                    Violation(
                        rule="max_discount",
                        severity="warning",
                        message=(
                            f"{patch.value:g}% exceeds your "
                            f"{constraints.max_discount_percent:g}% ceiling. Clamped."
                        ),
                        original_value=patch.value,
                        clamped_value=constraints.max_discount_percent,
                    )
                )
                clamped_patches[i] = patch.model_copy(
                    update={"value": constraints.max_discount_percent}
                )

    is_blocked = blocked(violations)
    risk = RiskLevel.REVIEW if is_blocked else (RiskLevel.MODERATE if violations else action.risk_level)

    return ValidationResult(
        valid=not is_blocked,
        action=action.model_copy(update={"patch": clamped_patches, "risk_level": risk}),
        violations=violations,
        clamped_patches=clamped_patches if violations else None,
    )


def validate_decision(
    actions: list[ProposedAction],
    profile: BusinessProfile,
) -> list[ValidationResult]:
    return [validate_action(a, profile) for a in actions]

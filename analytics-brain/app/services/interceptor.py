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

Rewritten for the current schema (Qwen Output Handling): the old brand-tweak / colour-
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
    AgentActionType,
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


def enforce_uplift(
    baseline_price: float,
    proposed_price: float,
    constraints: BusinessConstraints,
) -> tuple[float, list[Violation]]:
    """Clamp a proposed price increase to the merchant's uplift ceiling above
    baseline_price. Never blocks — an upward move can never sell below cost by
    definition, so there is no Layer 3 case here, only Layer 2's ceiling.

    Returns (final_price, violations), same shape as enforce_price.
    """
    violations: list[Violation] = []
    ceiling = round(baseline_price * (1 + constraints.max_uplift_percent / 100), 2)
    if proposed_price > ceiling:
        violations.append(
            Violation(
                rule="max_uplift",
                severity="warning",
                message=(
                    f"${proposed_price:.2f} exceeds your {constraints.max_uplift_percent:g}% "
                    f"uplift ceiling above the ${baseline_price:.2f} baseline. "
                    f"Clamped to ${ceiling:.2f}."
                ),
                original_value=proposed_price,
                clamped_value=ceiling,
            )
        )
        return ceiling, violations
    return round(proposed_price, 2), violations


def enforce_price_rebalance(
    new_price: float,
    *,
    baseline_price: float,
    cost_price: float,
    constraints: BusinessConstraints,
    product_id: str = "",
) -> tuple[float, str, bool]:
    """Route a PRICE_REBALANCE proposal through the correct floor/ceiling:
    enforce_price (margin floor + below-cost block) for a move down from
    baseline, enforce_uplift (uplift ceiling, never blocks) for a move at or
    above baseline. Mirrors enforce_action_discount's (value, message,
    is_blocked) return shape so callers handle both identically.
    """
    if new_price < baseline_price:
        final_price, violations = enforce_price(
            cost_price=cost_price, proposed_price=new_price,
            constraints=constraints, product_id=product_id,
        )
        if blocked(violations):
            message = next(
                (v.message for v in violations if v.severity == "blocked"),
                "Blocked by interceptor.",
            )
            return final_price, message, True
        return final_price, "; ".join(v.message for v in violations), False

    final_price, violations = enforce_uplift(baseline_price, new_price, constraints)
    return final_price, "; ".join(v.message for v in violations), False


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


# ─── AgentAction discount enforcement (decision-time + execution-time) ───────

def enforce_action_discount(
    action_type: AgentActionType,
    tool_args: dict,
    *,
    cost_price: float,
    price: float,
    constraints: BusinessConstraints,
    product_id: str = "",
) -> tuple[dict, str, bool]:
    """Run a Qwen-proposed discount-bearing action through the real Layer 2/3
    primitives before it becomes an AgentAction (decision time) or before its
    payload is applied to live state (execution time, defense in depth).

    FLASH_SALE / SCARCITY_PRICE are product-scoped — checked against that
    product's real cost_price and price, including the merchant's explicit
    per-product min_price (enforce_discount alone doesn't know about
    min_price, only enforce_price/margin_floor_price does — this closes that
    gap without changing enforce_discount itself).

    RECOVERY_OFFER is order-level (no single product to protect margin on),
    so it's checked on a normalized 0-100 scale: the Layer 2 ceiling clamp
    still runs through the same real enforce_discount primitive, while Layer
    3's below-cost check is a structural no-op here (100 * (1 - d/100) can
    only go negative above 100%, which discount_percent can never reach once
    the ceiling clamp has already run) — consistent with Layer 3 not
    conceptually applying to a discount with no single cost basis.

    Returns (clamped_tool_args, constraint_check_message, is_blocked).
    is_blocked=True means the caller MUST decline the action entirely — the
    returned tool_args are not safe to use. constraint_check_message is ""
    when nothing was clamped (matches brand_check's empty-string convention).
    Any other action_type (layout_morph, copy_rewrite, duplicate_merge)
    passes through unchanged — they carry no discount.
    """
    if action_type not in (
        AgentActionType.FLASH_SALE,
        AgentActionType.SCARCITY_PRICE,
        AgentActionType.RECOVERY_OFFER,
        AgentActionType.CART_DWELL_NUDGE,
    ):
        return tool_args, "", False

    try:
        discount = float(tool_args.get("discount_percent") or 0)
    except (TypeError, ValueError):
        discount = 0.0

    if action_type in (AgentActionType.RECOVERY_OFFER, AgentActionType.CART_DWELL_NUDGE):
        # Both are order-level (no single product to protect margin on) —
        # same normalized 0-100 scale, same "no below-cost concept" reasoning
        # documented in this function's own docstring for RECOVERY_OFFER.
        final_discount, violations = enforce_discount(
            cost_price=0.0, base_price=100.0,
            discount_percent=discount, constraints=constraints,
        )
    else:
        final_discount, violations = enforce_discount(
            cost_price=cost_price, base_price=price,
            discount_percent=discount, constraints=constraints,
        )
        if not blocked(violations):
            floor = margin_floor_price(
                cost_price, constraints.min_profit_margin_percent,
                constraints.min_price.get(product_id, 0.0),
            )
            discounted_price = price * (1 - final_discount / 100) if price > 0 else 0.0
            if floor > cost_price and discounted_price < floor and price > 0:
                floor_discount = max(0.0, round((1 - floor / price) * 100, 2))
                violations.append(Violation(
                    rule="min_price",
                    severity="warning",
                    message=(
                        f"{final_discount:g}% would sell below your ${floor:.2f} "
                        f"minimum for this product. Clamped to {floor_discount:g}%."
                    ),
                    original_value=final_discount,
                    clamped_value=floor_discount,
                ))
                final_discount = floor_discount

    if blocked(violations):
        message = next(
            (v.message for v in violations if v.severity == "blocked"),
            "Blocked by interceptor.",
        )
        return tool_args, message, True

    constraint_check = "; ".join(v.message for v in violations)
    clamped_args = dict(tool_args)
    clamped_args["discount_percent"] = final_discount
    return clamped_args, constraint_check, False

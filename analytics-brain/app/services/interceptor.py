from app.models.schemas import (
    ProposedAction, BusinessProfile, ValidationResult,
    Violation, JsonPatch, RiskLevel
)
import copy


def validate_action(action: ProposedAction, profile: BusinessProfile) -> ValidationResult:
    """
    Every proposed action passes through here before reaching the merchant.
    This layer is immutable — Qwen cannot override it.
    """
    violations: list[Violation] = []
    clamped_patches = [p.model_copy(deep=True) for p in action.patch]

    product_map = {p.id: p for p in profile.products}
    constraints = profile.constraints

    for i, patch in enumerate(clamped_patches):
        # ── Price floor enforcement ───────────────────────────────────────────
        if "/price" in patch.path and patch.op.value == "replace":
            product_id = _extract_product_id(patch.path)
            product = product_map.get(product_id)

            if product and isinstance(patch.value, (int, float)):
                min_margin_price = product.cost_price * (
                    1 + constraints.min_profit_margin_percent / 100
                )
                floor = max(
                    constraints.min_price.get(product_id, 0),
                    min_margin_price
                )

                if patch.value < floor:
                    clamped = round(floor, 2)
                    violations.append(Violation(
                        rule="min_profit_margin",
                        severity="warning",
                        message=(
                            f"Price ${patch.value} violates "
                            f"{constraints.min_profit_margin_percent}% minimum margin. "
                            f"Clamping to ${clamped}."
                        ),
                        original_value=patch.value,
                        clamped_value=clamped,
                    ))
                    clamped_patches[i] = patch.model_copy(update={"value": clamped})

        # ── Discount ceiling enforcement ──────────────────────────────────────
        if "/discount_percent" in patch.path and patch.op.value == "replace":
            if isinstance(patch.value, (int, float)):
                if patch.value > constraints.max_discount_percent:
                    clamped = constraints.max_discount_percent
                    violations.append(Violation(
                        rule="max_discount",
                        severity="warning",
                        message=(
                            f"Discount {patch.value}% exceeds maximum "
                            f"{constraints.max_discount_percent}%. Clamping."
                        ),
                        original_value=patch.value,
                        clamped_value=clamped,
                    ))
                    clamped_patches[i] = patch.model_copy(update={"value": clamped})

        # ── Brand color enforcement ───────────────────────────────────────────
        if "/color_accent" in patch.path and isinstance(patch.value, str):
            if (
                constraints.brand_colors
                and patch.value not in constraints.brand_colors
            ):
                clamped = constraints.brand_colors[0]
                violations.append(Violation(
                    rule="brand_color",
                    severity="warning",
                    message=(
                        f"Color {patch.value} outside brand palette. "
                        f"Clamping to {clamped}."
                    ),
                    original_value=patch.value,
                    clamped_value=clamped,
                ))
                clamped_patches[i] = patch.model_copy(update={"value": clamped})

    blocked = any(v.severity == "blocked" for v in violations)
    risk = RiskLevel.MODERATE if violations else action.risk_level

    return ValidationResult(
        valid=not blocked,
        action=action.model_copy(update={
            "patch": clamped_patches,
            "risk_level": risk,
        }),
        violations=violations,
        clamped_patches=clamped_patches if violations else None,
    )


def validate_decision(
    actions: list[ProposedAction],
    profile: BusinessProfile,
) -> list[ValidationResult]:
    return [validate_action(a, profile) for a in actions]


def _extract_product_id(path: str) -> str:
    # /products/prod_123/price → prod_123
    parts = path.split("/")
    try:
        idx = parts.index("products")
        return parts[idx + 1]
    except (ValueError, IndexError):
        return ""


# ─── Brand Guard Layer (Layer 2) ──────────────────────────────────────────────

def check_brand_tweak(
    tweak: dict,
    guard_rules: "BrandGuardRules",
) -> list["BrandWarning"]:
    """
    Called in real time as merchant tweaks brand settings.
    Returns Qwen's own warnings — written at brand generation time.
    These aren't generic alerts. They reference the specific brand.
    """
    from app.models.schemas import BrandWarning
    warnings = []
    field = tweak.get("field", "")
    value = tweak.get("value", "")

    # ── Color temperature conflict ─────────────────────────────────────────────
    if field in ("accent", "primary", "background") and guard_rules.warm_cool_lock:
        proposed_temp = _estimate_color_temperature(value)
        if proposed_temp and proposed_temp != guard_rules.warm_cool_lock.value:
            warnings.append(BrandWarning(
                rule="warm_cool_lock",
                severity="warning",
                # Qwen's own words — written when it built the brand
                message=guard_rules.color_warning_template,
                field=field,
                proposed_value=value,
            ))

    # ── Forbidden color combination ────────────────────────────────────────────
    if field in ("accent", "primary"):
        for combo in guard_rules.forbidden_combinations:
            if value in (combo.color_a, combo.color_b):
                warnings.append(BrandWarning(
                    rule="forbidden_combination",
                    severity="warning",
                    message=f"Color conflict detected: {combo.reason}",
                    field=field,
                    proposed_value=value,
                ))

    # ── Protected color override ───────────────────────────────────────────────
    if field == "primary" and value not in guard_rules.protected_colors:
        if guard_rules.protected_colors:
            warnings.append(BrandWarning(
                rule="protected_color",
                severity="info",
                message=(
                    f"Your primary brand color is protected by Qwen's brand analysis. "
                    f"Changing it may affect brand recognition across your store."
                ),
                field=field,
                proposed_value=value,
            ))

    # ── Layout variant forbidden ───────────────────────────────────────────────
    if field == "layout_variant" and value in [
        v.value for v in guard_rules.forbidden_layout_variants
    ]:
        warnings.append(BrandWarning(
            rule="forbidden_layout",
            severity="warning",
            message=(
                f"The '{value}' layout conflicts with your brand style. "
                f"Qwen selected your current layout to match your logo's character."
            ),
            field=field,
            proposed_value=value,
        ))

    return warnings


def _estimate_color_temperature(hex_color: str) -> str | None:
    """Rough warm/cool detection from hex RGB values."""
    try:
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        if r > b + 30:
            return "warm"
        elif b > r + 30:
            return "cool"
        return "neutral"
    except Exception:
        return None

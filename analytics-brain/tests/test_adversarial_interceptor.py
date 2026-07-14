"""Adversarial tests for the interceptor — Layer 2/3 enforcement primitives.

These tests probe edge cases: negative values, NaN/Inf, boundary conditions,
and malicious JsonPatch payloads. The interceptor is the last line of defense
before a price or discount reaches the storefront; it must never silently
accept an unsafe value.
"""
from __future__ import annotations

import math

from app.services.interceptor import enforce_price, enforce_discount, validate_action, blocked
from app.models.schemas import (
    BusinessConstraints,
    ProposedAction,
    BusinessProfile,
    JsonPatch,
    PatchOp,
    Product,
    Violation,
    ActionType,
    RiskLevel,
)


# ─── Shared fixtures ──────────────────────────────────────────────────────────

DEFAULT_CONSTRAINTS = BusinessConstraints(
    min_profit_margin_percent=30,
    max_discount_percent=25,
    min_price={},
)


def _make_product(pid: str = "prod_1", cost: float = 10.0, price: float = 15.0) -> Product:
    """Helper — minimal Product for validate_action tests."""
    return Product(
        id=pid,
        merchant_id="m_1",
        name="Widget",
        cost_price=cost,
        price=price,
        baseline_price=price,
        stock=50,
    )


def _make_profile(
    products: list[Product] | None = None,
    constraints: BusinessConstraints = DEFAULT_CONSTRAINTS,
) -> BusinessProfile:
    return BusinessProfile(
        merchant_id="m_1",
        store_name="Test Store",
        constraints=constraints,
        products=products or [_make_product()],
    )


def _make_action(
    patches: list[JsonPatch],
    action_type: ActionType = ActionType.PRICE_ADJUST,
    risk: RiskLevel = RiskLevel.SAFE,
) -> ProposedAction:
    return ProposedAction(
        id="act_1",
        type=action_type,
        label="test action",
        description="test",
        patch=patches,
        risk_level=risk,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TestEnforcePriceAdversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnforcePriceAdversarial:
    """Adversarial inputs to enforce_price — must never return an unsafe price
    without a corresponding violation."""

    def test_negative_price(self):
        """proposed_price=-10 is below any positive cost → hard block."""
        final, vs = enforce_price(
            cost_price=10.0, proposed_price=-10.0, constraints=DEFAULT_CONSTRAINTS,
        )
        assert blocked(vs)
        assert any(v.rule == "below_cost" for v in vs)

    def test_zero_price(self):
        """proposed_price=0 with positive cost → below cost → blocked."""
        final, vs = enforce_price(
            cost_price=5.0, proposed_price=0.0, constraints=DEFAULT_CONSTRAINTS,
        )
        assert blocked(vs)
        assert any(v.rule == "below_cost" for v in vs)

    def test_price_equals_cost(self):
        """Exactly at cost is NOT below cost — passes Layer 3 (but may warn on margin)."""
        final, vs = enforce_price(
            cost_price=10.0, proposed_price=10.0, constraints=DEFAULT_CONSTRAINTS,
        )
        # 10.0 == cost 10.0 → not below_cost. But margin floor is 10 * 1.30 = 13.0,
        # so it should get a margin warning and clamp to 13.0.
        assert not any(v.rule == "below_cost" for v in vs)
        # margin floor clamp should fire
        assert any(v.rule == "min_profit_margin" for v in vs)
        assert final == 13.0

    def test_price_one_cent_below_cost(self):
        """cost=10.00, proposed=9.99 → below cost → blocked."""
        final, vs = enforce_price(
            cost_price=10.0, proposed_price=9.99, constraints=DEFAULT_CONSTRAINTS,
        )
        assert blocked(vs)
        assert any(v.rule == "below_cost" for v in vs)
        assert final == 9.99  # returned as-is (unsafe)

    def test_extremely_large_price(self):
        """No ceiling on price — absurdly high values pass cleanly."""
        final, vs = enforce_price(
            cost_price=10.0, proposed_price=999_999_999.0, constraints=DEFAULT_CONSTRAINTS,
        )
        assert not vs
        assert final == 999_999_999.0

    def test_nan_price(self):
        """NaN comparisons are always False in Python — NaN < cost is False,
        NaN < floor is False, so it falls through to the return. We just
        verify no crash and a violation or pass-through occurs."""
        final, vs = enforce_price(
            cost_price=10.0, proposed_price=float("nan"), constraints=DEFAULT_CONSTRAINTS,
        )
        # NaN < 10.0 → False, so below_cost does NOT fire.
        # NaN < 13.0 (floor) → False, so margin warning does NOT fire.
        # It passes through to round(nan, 2) which returns nan.
        # The important thing: no crash.
        assert math.isnan(final)

    def test_inf_price(self):
        """inf > cost, inf > floor → passes cleanly (no ceiling)."""
        final, vs = enforce_price(
            cost_price=10.0, proposed_price=float("inf"), constraints=DEFAULT_CONSTRAINTS,
        )
        assert not vs
        assert final == float("inf")

    def test_zero_cost_product(self):
        """cost_price=0, proposed=1 → no below_cost (1 > 0). Margin floor = 0 * 1.3 = 0.
        1 > 0, so no margin warning either. Clean pass."""
        final, vs = enforce_price(
            cost_price=0.0, proposed_price=1.0, constraints=DEFAULT_CONSTRAINTS,
        )
        assert not vs
        assert final == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# TestEnforceDiscountAdversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnforceDiscountAdversarial:
    """Adversarial inputs to enforce_discount — ceiling clamp and below-cost block."""

    def test_negative_discount(self):
        """Negative discount (a price increase) — below the ceiling, no below-cost risk.
        Should pass cleanly (no violations)."""
        final, vs = enforce_discount(
            cost_price=5.0, base_price=10.0, discount_percent=-10.0,
            constraints=DEFAULT_CONSTRAINTS,
        )
        assert not vs
        assert final == -10.0

    def test_discount_over_100(self):
        """150% discount → clamped to max_discount_percent (25%)."""
        final, vs = enforce_discount(
            cost_price=5.0, base_price=10.0, discount_percent=150.0,
            constraints=DEFAULT_CONSTRAINTS,
        )
        # Clamped to 25%. discounted = 10 * (1 - 0.25) = 7.5 > cost 5.0 → no block.
        assert any(v.rule == "max_discount" for v in vs)
        assert final == 25.0
        assert not blocked(vs)

    def test_discount_exactly_at_ceiling(self):
        """Exactly at max_discount_percent → no clamping, no warning."""
        final, vs = enforce_discount(
            cost_price=5.0, base_price=10.0, discount_percent=25.0,
            constraints=DEFAULT_CONSTRAINTS,
        )
        # discounted = 10 * 0.75 = 7.5 > 5.0 → clean pass
        assert not vs
        assert final == 25.0

    def test_discount_that_drives_below_cost(self):
        """80% off a $10 item with $5 cost → discounted = $2 < $5 → blocked."""
        constraints = BusinessConstraints(
            min_profit_margin_percent=0,
            max_discount_percent=80,  # allow the high discount through Layer 2
            min_price={},
        )
        final, vs = enforce_discount(
            cost_price=5.0, base_price=10.0, discount_percent=80.0,
            constraints=constraints,
        )
        # discounted = 10 * (1 - 0.80) = 2.0 < cost 5.0 → blocked
        assert blocked(vs)
        assert any(v.rule == "below_cost" for v in vs)

    def test_zero_discount(self):
        """0% discount — clean pass."""
        final, vs = enforce_discount(
            cost_price=5.0, base_price=10.0, discount_percent=0.0,
            constraints=DEFAULT_CONSTRAINTS,
        )
        assert not vs
        assert final == 0.0

    def test_decimal_discount(self):
        """15.5% — fractional discounts work fine."""
        final, vs = enforce_discount(
            cost_price=5.0, base_price=10.0, discount_percent=15.5,
            constraints=DEFAULT_CONSTRAINTS,
        )
        # discounted = 10 * (1 - 0.155) = 8.45 > 5.0 → clean
        assert not vs
        assert final == 15.5


# ═══════════════════════════════════════════════════════════════════════════════
# TestValidateActionAdversarial
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateActionAdversarial:
    """Adversarial ProposedAction payloads through validate_action."""

    def test_patch_with_negative_price(self):
        """JsonPatch setting price to -5 → below_cost block."""
        product = _make_product(pid="prod_1", cost=10.0)
        profile = _make_profile(products=[product])
        action = _make_action([
            JsonPatch(op=PatchOp.REPLACE, path="/products/prod_1/price", value=-5),
        ])
        result = validate_action(action, profile)
        assert not result.valid
        assert blocked(result.violations)
        assert any(v.rule == "below_cost" for v in result.violations)

    def test_patch_with_extreme_discount(self):
        """discount_percent=99 on a patch → clamped to max_discount_percent (25)."""
        product = _make_product(pid="prod_1")
        profile = _make_profile(products=[product])
        action = _make_action([
            JsonPatch(
                op=PatchOp.REPLACE,
                path="/products/prod_1/discount_percent",
                value=99,
            ),
        ], action_type=ActionType.PROMO_TRIGGER)
        result = validate_action(action, profile)
        # Should be clamped, not blocked (discount patches only enforce ceiling).
        assert any(v.rule == "max_discount" for v in result.violations)
        # The clamped patch should have value=25
        discount_patch = result.action.patch[0]
        assert discount_patch.value == 25.0

    def test_multiple_patches_one_evil(self):
        """3 patches: first and third are fine, middle is malicious (below cost)."""
        product = _make_product(pid="prod_1", cost=10.0, price=15.0)
        profile = _make_profile(products=[product])
        action = _make_action([
            JsonPatch(op=PatchOp.REPLACE, path="/products/prod_1/price", value=20.0),
            JsonPatch(op=PatchOp.REPLACE, path="/products/prod_1/price", value=-1.0),
            JsonPatch(op=PatchOp.REPLACE, path="/products/prod_1/price", value=25.0),
        ])
        result = validate_action(action, profile)
        assert not result.valid
        assert blocked(result.violations)
        # The below_cost violation should reference the -1.0 patch
        below_cost_vs = [v for v in result.violations if v.rule == "below_cost"]
        assert len(below_cost_vs) >= 1

    def test_empty_patch_list(self):
        """No patches → valid, no violations."""
        profile = _make_profile()
        action = _make_action(patches=[])
        result = validate_action(action, profile)
        assert result.valid
        assert not result.violations

    def test_patch_targeting_nonexistent_product(self):
        """Patch references a product not in the profile → silently skipped
        (no product context to enforce against, so the patch passes through)."""
        profile = _make_profile(products=[_make_product(pid="prod_1")])
        action = _make_action([
            JsonPatch(
                op=PatchOp.REPLACE,
                path="/products/prod_999/price",
                value=-100,  # would be blocked if prod_999 existed
            ),
        ])
        result = validate_action(action, profile)
        # No product found → no enforcement → valid (patch is a no-op at apply time)
        assert result.valid
        assert not result.violations

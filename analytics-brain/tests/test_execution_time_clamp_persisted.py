"""Regression coverage for a real bug found while capturing a demo
screenshot: a merchant overrode a flash_sale discount to 70% (ceiling is
40%) on approval. The interceptor correctly clamped the LIVE promo to a
safe value (protecting the storefront), but _register_promo/_register_
recovery/_register_price_rebalance only used the clamped value to build the
live Promo/RecoveryOffer/Product.price — they never wrote it back onto the
AgentActionDB row. So the DB row, the ledger receipt, and the API response
the merchant sees all kept showing the pre-clamp number with no warning,
even though the interceptor had already done its job on the real store
state. These tests assert the row itself now reflects what was actually
applied."""
import asyncio
from unittest.mock import AsyncMock, patch

from app.models.db_models import AgentActionDB
from app.models.schemas import BusinessConstraints, SystemState, Product


def _action(action_type: str, payload: dict) -> AgentActionDB:
    return AgentActionDB(
        id="act1", merchant_id="m1", promo_id="promo1", action_type=action_type,
        trigger="t", title="t", description="d", estimated_gmv=0.0,
        estimated_confidence=0.9, payload=payload, brand_check="", status="pending",
        created_at=0,
    )


def _run(coro):
    return asyncio.run(coro)


class TestRegisterPromoPersistsClampedValue:
    def test_flash_sale_override_above_ceiling_is_persisted_clamped_not_raw(self):
        from app.routers.agent import _register_promo

        row = _action("flash_sale", {"discount_percent": 70.0, "product_id": "p1"})
        product = Product(
            id="p1", merchant_id="m1", name="Widget", price=45.0, cost_price=27.0,
            baseline_price=45.0, stock=10, category="slides",
        )
        state = SystemState(version=1, last_updated=0, products={"p1": product})

        with (
            patch("app.services.delta.load_state", new_callable=AsyncMock, return_value=state),
            patch("app.services.delta.save_state", new_callable=AsyncMock),
            patch(
                "app.services.profile.load_constraints", new_callable=AsyncMock,
                return_value=BusinessConstraints(max_discount_percent=40.0, min_profit_margin_percent=15.0),
            ),
        ):
            result = _run(_register_promo(row, "{d}% off {name}", row.payload, db=None))

        assert result is True
        # The row must reflect what was ACTUALLY applied, not the raw 70% ask.
        assert row.payload["discount_percent"] < 70.0
        assert row.payload["discount_percent"] <= 40.0
        assert row.constraint_check  # a warning must be recorded, not silence

    def test_flash_sale_within_ceiling_is_unchanged(self):
        """A discount that never needed clamping shouldn't gain a spurious
        constraint_check or a mutated payload."""
        from app.routers.agent import _register_promo

        row = _action("flash_sale", {"discount_percent": 10.0, "product_id": "p1"})
        product = Product(
            id="p1", merchant_id="m1", name="Widget", price=45.0, cost_price=27.0,
            baseline_price=45.0, stock=10, category="slides",
        )
        state = SystemState(version=1, last_updated=0, products={"p1": product})

        with (
            patch("app.services.delta.load_state", new_callable=AsyncMock, return_value=state),
            patch("app.services.delta.save_state", new_callable=AsyncMock),
            patch(
                "app.services.profile.load_constraints", new_callable=AsyncMock,
                return_value=BusinessConstraints(max_discount_percent=40.0, min_profit_margin_percent=15.0),
            ),
        ):
            result = _run(_register_promo(row, "{d}% off {name}", row.payload, db=None))

        assert result is True
        assert row.payload["discount_percent"] == 10.0


class TestRegisterRecoveryPersistsClampedValue:
    def test_recovery_offer_override_above_ceiling_is_persisted_clamped(self):
        from app.routers.agent import _register_recovery

        row = _action("recovery_offer", {"discount_percent": 90.0})
        state = SystemState(version=1, last_updated=0, products={})

        with (
            patch("app.services.delta.load_state", new_callable=AsyncMock, return_value=state),
            patch("app.services.delta.save_state", new_callable=AsyncMock),
            patch(
                "app.services.profile.load_constraints", new_callable=AsyncMock,
                return_value=BusinessConstraints(max_discount_percent=40.0),
            ),
        ):
            result = _run(_register_recovery(row, row.payload, db=None))

        assert result is True
        assert row.payload["discount_percent"] < 90.0
        assert row.payload["discount_percent"] <= 40.0
        assert row.constraint_check


class TestRegisterPriceRebalancePersistsClampedValue:
    def test_price_rebalance_below_margin_floor_is_persisted_clamped(self):
        from app.routers.agent import _register_price_rebalance

        # $29 is above cost ($27, so not a hard block) but below the 15%
        # margin floor (~$31.76) — the case that should CLAMP, not block.
        row = _action("price_rebalance", {"product_id": "p1", "new_price": 29.0})
        product = AsyncMock()
        product.id = "p1"
        product.merchant_id = "m1"
        product.is_active = True
        product.price = 45.0
        product.baseline_price = 45.0
        product.cost_price = 27.0

        db = AsyncMock()
        db.get = AsyncMock(return_value=product)
        db.flush = AsyncMock()

        with (
            patch("app.services.profile.load_constraints", new_callable=AsyncMock,
                  return_value=BusinessConstraints(min_profit_margin_percent=15.0)),
            patch("app.routers.products._sync_state_if_live", new_callable=AsyncMock),
        ):
            result = _run(_register_price_rebalance(row, row.payload, db=db))

        assert result is True
        # $29 is below the margin floor — must be clamped up, not applied raw.
        assert row.payload["new_price"] > 29.0
        assert row.constraint_check

"""Checkout must apply a cart_dwell_nudge discount ONLY to the session it
was scoped to — this is the end-to-end proof that the original bug (any
customer checking out during an active recovery/dwell window got the
discount) is actually fixed at the money-math layer, not just in cart
display."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import RecoveryOffer, SystemState, OrderCustomer, Cart, CartItem


def _run(coro):
    return asyncio.run(coro)


def _rowcount_execute_result():
    m = AsyncMock()
    m.rowcount = 1
    return m


class TestCheckoutSessionScopedDiscount:
    def test_session_with_dwell_offer_gets_discount(self):
        from app.services import orders as orders_svc
        from app.services import cart as cart_svc

        cart = Cart(
            session_id="sess-A", merchant_id="m1",
            items=[CartItem(product_id="p1", name="Widget", unit_price=100.0, qty=1, line_total=100.0)],
            subtotal=100.0, item_count=1, total=100.0, updated_at=0,
        )
        dwell = RecoveryOffer(percent=20, label="dwell", expires_at=9999999999999, promo_id="promo-dwell")

        async def fake_get_cart(merchant_id, session_id):
            c = cart.model_copy(deep=True)
            return await cart_svc._apply_recovery(merchant_id, c)

        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=SystemState(version=1, last_updated=0, products={})),
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, side_effect=lambda m, s: dwell if s == "sess-A" else None),
            patch("app.services.orders.cart_svc.get_cart", side_effect=fake_get_cart),
            patch("app.services.orders.cart_svc.clear_cart", new_callable=AsyncMock),
            patch("app.services.orders.delta_svc.load_state", new_callable=AsyncMock, return_value=SystemState(version=1, last_updated=0, products={})),
            patch("app.services.orders._sync_state_after_stock_change", new_callable=AsyncMock),
        ):
            db = AsyncMock()
            db.execute = AsyncMock(return_value=_rowcount_execute_result())
            db.commit = AsyncMock()
            db.add = MagicMock()  # db.add is sync in SQLAlchemy's AsyncSession API

            order = _run(orders_svc.checkout(db, "m1", "sess-A", OrderCustomer(name="A", email="a@x.com")))

        assert order.subtotal == 100.0
        assert order.total == 80.0  # 20% off
        assert "promo-dwell" in (order.promo_applied or "")

    def test_different_session_never_gets_this_sessions_dwell_discount(self):
        """The exact regression this whole phase exists to prevent."""
        from app.services import orders as orders_svc
        from app.services import cart as cart_svc

        cart = Cart(
            session_id="sess-B", merchant_id="m1",
            items=[CartItem(product_id="p1", name="Widget", unit_price=100.0, qty=1, line_total=100.0)],
            subtotal=100.0, item_count=1, total=100.0, updated_at=0,
        )
        dwell = RecoveryOffer(percent=20, label="dwell", expires_at=9999999999999, promo_id="promo-dwell")

        async def fake_get_cart(merchant_id, session_id):
            c = cart.model_copy(deep=True)
            return await cart_svc._apply_recovery(merchant_id, c)

        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=SystemState(version=1, last_updated=0, products={})),
            # dwell offer only exists for sess-A, never sess-B
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, side_effect=lambda m, s: dwell if s == "sess-A" else None),
            patch("app.services.orders.cart_svc.get_cart", side_effect=fake_get_cart),
            patch("app.services.orders.cart_svc.clear_cart", new_callable=AsyncMock),
            patch("app.services.orders.delta_svc.load_state", new_callable=AsyncMock, return_value=SystemState(version=1, last_updated=0, products={})),
            patch("app.services.orders._sync_state_after_stock_change", new_callable=AsyncMock),
        ):
            db = AsyncMock()
            db.execute = AsyncMock(return_value=_rowcount_execute_result())
            db.commit = AsyncMock()
            db.add = MagicMock()  # db.add is sync in SQLAlchemy's AsyncSession API

            order = _run(orders_svc.checkout(db, "m1", "sess-B", OrderCustomer(name="B", email="b@x.com")))

        assert order.total == 100.0  # NO discount — session B never dwelled
        assert order.promo_applied is None

    def test_store_wide_recovery_offer_still_applies_to_any_session(self):
        """Regression guard: recovery_offer's existing store-wide behavior
        (intentional, not the bug) must survive checkout's refactor too."""
        from app.services import orders as orders_svc
        from app.services import cart as cart_svc

        cart = Cart(
            session_id="sess-C", merchant_id="m1",
            items=[CartItem(product_id="p1", name="Widget", unit_price=100.0, qty=1, line_total=100.0)],
            subtotal=100.0, item_count=1, total=100.0, updated_at=0,
        )
        recovery = RecoveryOffer(percent=10, label="storewide", expires_at=9999999999999, promo_id="promo-storewide")
        state_with_recovery = SystemState(version=1, last_updated=0, products={}, recovery=recovery)

        async def fake_get_cart(merchant_id, session_id):
            c = cart.model_copy(deep=True)
            return await cart_svc._apply_recovery(merchant_id, c)

        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=state_with_recovery),
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, return_value=None),
            patch("app.services.orders.cart_svc.get_cart", side_effect=fake_get_cart),
            patch("app.services.orders.cart_svc.clear_cart", new_callable=AsyncMock),
            patch("app.services.orders.delta_svc.load_state", new_callable=AsyncMock, return_value=state_with_recovery),
            patch("app.services.orders._sync_state_after_stock_change", new_callable=AsyncMock),
        ):
            db = AsyncMock()
            db.execute = AsyncMock(return_value=_rowcount_execute_result())
            db.commit = AsyncMock()
            db.add = MagicMock()  # db.add is sync in SQLAlchemy's AsyncSession API

            order = _run(orders_svc.checkout(db, "m1", "sess-C", OrderCustomer(name="C", email="c@x.com")))

        assert order.total == 90.0  # 10% off, applies to a session that never dwelled
        assert "promo-storewide" in (order.promo_applied or "")

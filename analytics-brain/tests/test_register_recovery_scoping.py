"""_register_recovery must route cart_dwell_nudge to the per-session dwell
key and recovery_offer to the store-wide SystemState.recovery field — never
the other way, and never both."""
import asyncio
from unittest.mock import AsyncMock, patch

from app.models.db_models import AgentActionDB
from app.models.schemas import BusinessConstraints


def _action(action_type: str, payload: dict) -> AgentActionDB:
    return AgentActionDB(
        id="act1", merchant_id="m1", promo_id="promo1", action_type=action_type,
        trigger="t", title="t", description="d", estimated_gmv=0.0,
        estimated_confidence=0.9, payload=payload, brand_check="", status="pending",
        created_at=0,
    )


def _run(coro):
    return asyncio.run(coro)


class TestRegisterRecoveryScoping:
    def test_cart_dwell_nudge_writes_session_scoped_offer_not_state(self):
        from app.routers.agent import _register_recovery
        from app.models.schemas import SystemState

        row = _action("cart_dwell_nudge", {"discount_percent": 8, "session_id": "sess-A"})
        state = SystemState(version=1, last_updated=0, products={})

        with (
            patch("app.services.delta.load_state", new_callable=AsyncMock, return_value=state),
            patch("app.services.delta.save_state", new_callable=AsyncMock) as mock_save_state,
            patch("app.services.profile.load_constraints", new_callable=AsyncMock, return_value=BusinessConstraints()),
            patch("app.services.cart.set_dwell_offer", new_callable=AsyncMock) as mock_set_dwell,
        ):
            result = _run(_register_recovery(row, row.payload, db=None))

        assert result is True
        mock_set_dwell.assert_awaited_once()
        called_merchant_id, called_session_id, called_offer = mock_set_dwell.call_args.args
        assert called_merchant_id == "m1"
        assert called_session_id == "sess-A"
        assert called_offer.percent == 8
        mock_save_state.assert_not_awaited()  # must NOT touch store-wide state

    def test_cart_dwell_nudge_without_session_id_declines(self):
        """No session_id in payload means this shouldn't fall back to a
        store-wide effect — decline rather than silently reintroducing the
        original bug."""
        from app.routers.agent import _register_recovery
        from app.models.schemas import SystemState

        row = _action("cart_dwell_nudge", {"discount_percent": 8})  # no session_id
        state = SystemState(version=1, last_updated=0, products={})

        with (
            patch("app.services.delta.load_state", new_callable=AsyncMock, return_value=state),
            patch("app.services.delta.save_state", new_callable=AsyncMock) as mock_save_state,
            patch("app.services.profile.load_constraints", new_callable=AsyncMock, return_value=BusinessConstraints()),
            patch("app.services.cart.set_dwell_offer", new_callable=AsyncMock) as mock_set_dwell,
        ):
            result = _run(_register_recovery(row, row.payload, db=None))

        assert result is False
        mock_set_dwell.assert_not_awaited()
        mock_save_state.assert_not_awaited()

    def test_recovery_offer_still_writes_store_wide_state(self):
        """Regression guard: recovery_offer's existing store-wide behavior
        must be byte-identical after the split."""
        from app.routers.agent import _register_recovery
        from app.models.schemas import SystemState

        row = _action("recovery_offer", {"discount_percent": 12})
        state = SystemState(version=1, last_updated=0, products={})

        with (
            patch("app.services.delta.load_state", new_callable=AsyncMock, return_value=state),
            patch("app.services.delta.save_state", new_callable=AsyncMock) as mock_save_state,
            patch("app.services.profile.load_constraints", new_callable=AsyncMock, return_value=BusinessConstraints()),
            patch("app.services.cart.set_dwell_offer", new_callable=AsyncMock) as mock_set_dwell,
        ):
            result = _run(_register_recovery(row, row.payload, db=None))

        assert result is True
        mock_set_dwell.assert_not_awaited()
        mock_save_state.assert_awaited_once()
        saved_state = mock_save_state.call_args.args[1]
        assert saved_state.recovery.percent == 12

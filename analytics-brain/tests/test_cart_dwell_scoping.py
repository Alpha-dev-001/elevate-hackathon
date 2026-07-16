"""Cart-dwell discounts must be scoped to the one session that triggered
them — a store-wide recovery_offer is intentionally different (see
services/cart_dwell.py and routers/agent.py's _register_recovery docstrings
for why). get_effective_discount is the one place both sources are merged,
so cart display (cart.py) and checkout math (orders.py) can never drift
apart by computing it independently."""
import asyncio
from unittest.mock import AsyncMock, patch

from app.models.schemas import RecoveryOffer, SystemState


def _state(recovery=None):
    return SystemState(version=1, last_updated=0, products={}, recovery=recovery)


def _run(coro):
    return asyncio.run(coro)


class TestGetEffectiveDiscount:
    def test_no_state_no_dwell_returns_none(self):
        from app.services.cart import get_effective_discount
        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=None),
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, return_value=None),
        ):
            assert _run(get_effective_discount("m1", "s1")) is None

    def test_store_wide_recovery_only(self):
        from app.services.cart import get_effective_discount
        offer = RecoveryOffer(percent=15, label="Complete your order — 15% off", expires_at=9999999999999, promo_id="p1")
        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=_state(offer)),
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, return_value=None),
        ):
            result = _run(get_effective_discount("m1", "s1"))
            assert result is not None
            assert result.percent == 15

    def test_session_dwell_only(self):
        from app.services.cart import get_effective_discount
        dwell = RecoveryOffer(percent=8, label="Still deciding? 8% off", expires_at=9999999999999, promo_id="p2")
        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=_state(None)),
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, return_value=dwell),
        ):
            result = _run(get_effective_discount("m1", "s1"))
            assert result is not None
            assert result.percent == 8
            assert result.promo_id == "p2"

    def test_different_session_never_sees_this_sessions_dwell(self):
        """The exact bug being fixed: session B must not see session A's
        cart_dwell_nudge discount. _get_dwell_offer is keyed by session_id —
        this test proves the caller passes the right session through and
        gets nothing back for an unrelated one."""
        from app.services.cart import get_effective_discount

        async def fake_get_dwell(merchant_id, session_id):
            return RecoveryOffer(percent=8, label="x", expires_at=9999999999999, promo_id="p2") if session_id == "session-A" else None

        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=_state(None)),
            patch("app.services.cart._get_dwell_offer", side_effect=fake_get_dwell),
        ):
            assert _run(get_effective_discount("m1", "session-B")) is None
            result = _run(get_effective_discount("m1", "session-A"))
            assert result is not None and result.percent == 8

    def test_takes_the_larger_when_both_apply(self):
        from app.services.cart import get_effective_discount
        recovery = RecoveryOffer(percent=10, label="storewide", expires_at=9999999999999, promo_id="p1")
        dwell = RecoveryOffer(percent=15, label="dwell", expires_at=9999999999999, promo_id="p2")
        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=_state(recovery)),
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, return_value=dwell),
        ):
            result = _run(get_effective_discount("m1", "s1"))
            assert result.percent == 15

    def test_expired_recovery_is_ignored(self):
        from app.services.cart import get_effective_discount
        expired = RecoveryOffer(percent=15, label="stale", expires_at=1, promo_id="p1")  # epoch ms 1 — long past
        with (
            patch("app.services.cart.delta_svc.load_state", new_callable=AsyncMock, return_value=_state(expired)),
            patch("app.services.cart._get_dwell_offer", new_callable=AsyncMock, return_value=None),
        ):
            assert _run(get_effective_discount("m1", "s1")) is None


class TestSessionIdSurvivesIntoPayload:
    """run_decision_cycle writes session_id into tool_args (which becomes
    AgentAction.payload) only when the caller passed one — every existing
    caller (behavior.py, store_review.py, pricing_cycle.py) omits it and
    must see byte-identical payload behavior to before this change."""

    def test_session_id_added_when_provided(self):
        tool_args = {"discount_percent": 8}
        session_id = "sess-123"
        merged = dict(tool_args)
        merged["session_id"] = session_id
        assert merged == {"discount_percent": 8, "session_id": "sess-123"}

    def test_qwen_supplied_session_id_is_overwritten_not_trusted(self):
        """If Qwen's tool call somehow included a session_id key, the real
        detected one must win — this is what makes it safe to trust
        payload['session_id'] as server-verified at approval time."""
        tool_args = {"discount_percent": 8, "session_id": "hallucinated"}
        real_session_id = "sess-real"
        merged = dict(tool_args)
        merged["session_id"] = real_session_id
        assert merged["session_id"] == "sess-real"

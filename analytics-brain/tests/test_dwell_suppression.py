"""cart_dwell_nudge must not re-fire for the same still-dwelling session on
every 60s tick — a real gap found live: the merchant saw a fresh card for the
same dwelling cart roughly every time the previous one resolved, with no
cooldown at all (unlike duplicate_merge, which already suppresses re-firing
for a dismissed group). suppress_dwell_session/_is_dwell_suppressed close
that gap; find_duplicate_group's own precedent is the pattern to match."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.db_models import AgentActionDB
from app.models.schemas import BusinessConstraints


def _run(coro):
    return asyncio.run(coro)


class TestSuppressDwellSession:
    def test_suppressed_session_is_reported_suppressed(self):
        from app.services.cart_dwell import suppress_dwell_session, _is_dwell_suppressed

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)

        _run(suppress_dwell_session("m1", "sess-A", redis_mock))
        redis_mock.set.assert_awaited_once()
        # The TTL kwarg must actually be passed (not indefinite, not omitted).
        _, kwargs = redis_mock.set.call_args
        assert kwargs.get("ex") == 30 * 60

    def test_unsuppressed_session_reports_false(self):
        from app.services.cart_dwell import _is_dwell_suppressed

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        assert _run(_is_dwell_suppressed("m1", "sess-B", redis_mock)) is False

    def test_suppressed_session_reports_true(self):
        from app.services.cart_dwell import _is_dwell_suppressed

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value="1")
        assert _run(_is_dwell_suppressed("m1", "sess-A", redis_mock)) is True

    def test_different_session_not_cross_suppressed(self):
        """Suppressing session A must never affect session B — same
        per-session-key isolation as the dwell offer itself."""
        from app.services.cart_dwell import _is_dwell_suppressed

        async def fake_get(key):
            return "1" if "sess-A" in key else None

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(side_effect=fake_get)
        assert _run(_is_dwell_suppressed("m1", "sess-A", redis_mock)) is True
        assert _run(_is_dwell_suppressed("m1", "sess-B", redis_mock)) is False


class TestRunDwellCheckSkipsSuppressed:
    def test_suppressed_session_never_reaches_decision_cycle(self):
        from app.services import cart_dwell as dwell_mod
        from app.models.schemas import Cart

        merchant = type("M", (), {"id": "m1", "is_live": True})()
        dwelling_cart = Cart(
            session_id="sess-A", merchant_id="m1",
            items=[{"product_id": "p1", "name": "Widget", "unit_price": 10.0, "qty": 1, "line_total": 10.0}],
            subtotal=10.0, item_count=1, total=10.0, updated_at=0,  # updated_at=0 is always "dwelling"
        )

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [merchant]
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)

        redis_mock = AsyncMock()
        redis_mock.smembers = AsyncMock(return_value={"sess-A"})

        with (
            patch("app.services.cart.get_cart", new_callable=AsyncMock, return_value=dwelling_cart),
            patch("app.services.cart_dwell.session_has_abandoned", new_callable=AsyncMock, return_value=False),
            patch("app.services.cart_dwell._is_dwell_suppressed", new_callable=AsyncMock, return_value=True),
            patch("app.services.decision_engine.run_decision_cycle", new_callable=AsyncMock) as mock_cycle,
        ):
            fired = _run(dwell_mod.run_dwell_check(db, redis_mock))

        assert fired == 0
        mock_cycle.assert_not_awaited()

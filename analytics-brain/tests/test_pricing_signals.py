from app.services.pricing_signals import count_signals_for_product


def test_counts_only_matching_product():
    events = [
        {"product_id": "p1", "event_type": "view"},
        {"product_id": "p2", "event_type": "view"},
        {"product_id": "p1", "event_type": "add_to_cart"},
        {"product_id": "p1", "event_type": "purchase"},
        {"product_id": "p1", "event_type": "view"},
    ]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 2, "cart_adds": 1}


def test_no_matching_events_returns_zeros():
    events = [{"product_id": "p2", "event_type": "view"}]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 0, "cart_adds": 0}


def test_ignores_non_counted_event_types():
    events = [
        {"product_id": "p1", "event_type": "hover"},
        {"product_id": "p1", "event_type": "abandon"},
        {"product_id": "p1", "event_type": "purchase"},
    ]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 0, "cart_adds": 0}


from app.services.pricing_signals import is_suspicious


def test_high_views_near_zero_cart_adds_is_suspicious():
    # 5x trailing average, cart_adds effectively zero relative to that view count.
    assert is_suspicious(today_views=100, today_cart_adds=0, trailing_avg_views=20.0) is True


def test_high_views_with_real_cart_adds_is_not_suspicious():
    # Same view spike, but genuine engagement (cart_adds proportional to views).
    assert is_suspicious(today_views=100, today_cart_adds=15, trailing_avg_views=20.0) is False


def test_normal_day_is_not_suspicious():
    assert is_suspicious(today_views=22, today_cart_adds=3, trailing_avg_views=20.0) is False


def test_zero_trailing_average_never_flags():
    # No baseline to compare against (brand-new product) — can't call it
    # suspicious with nothing to be anomalous relative to.
    assert is_suspicious(today_views=50, today_cart_adds=0, trailing_avg_views=0.0) is False


# ---------------------------------------------------------------------------
# run_daily_rollup_if_due — regression coverage for a real bug found live:
# rollup_daily_signals and flag_suspicious_signals were both fully written
# and tested at the pure-function level, but NEITHER was ever called from
# anywhere in the app (not main.py, not pricing_cycle's tick, nowhere).
# product_price_history had 0 rows in the live database as a result, which
# meant is_price_rebalance_eligible was unconditionally False for every
# product, forever — price_rebalance had literally never fired in
# production. This section covers the wiring gap itself, not just the pure
# logic underneath it, since pure-function tests alone didn't catch it.
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, patch

from app.core.redis import Keys
from app.services.pricing_signals import should_run_daily_rollup, run_daily_rollup_if_due


def _run(coro):
    return asyncio.run(coro)


class TestShouldRunDailyRollup:
    def test_never_run_is_due(self):
        assert should_run_daily_rollup(None, "2026-07-17") is True

    def test_already_run_today_is_not_due(self):
        assert should_run_daily_rollup("2026-07-17", "2026-07-17") is False

    def test_run_for_a_different_day_is_due(self):
        assert should_run_daily_rollup("2026-07-16", "2026-07-17") is True


class TestRunDailyRollupIfDue:
    def test_skips_when_already_run_for_target_date(self):
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value="2026-07-16")  # matches _yesterday_utc() below
        db_mock = AsyncMock()

        with (
            patch("app.services.pricing_signals._yesterday_utc", return_value="2026-07-16"),
            patch("app.services.pricing_signals.rollup_daily_signals", new_callable=AsyncMock) as mock_rollup,
            patch("app.services.pricing_signals.flag_suspicious_signals", new_callable=AsyncMock) as mock_flag,
        ):
            result = _run(run_daily_rollup_if_due(db_mock, redis_mock))

        assert result == 0
        mock_rollup.assert_not_awaited()
        mock_flag.assert_not_awaited()
        redis_mock.set.assert_not_awaited()

    def test_runs_and_marks_done_when_due(self):
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)  # never run
        db_mock = AsyncMock()

        with (
            patch("app.services.pricing_signals._yesterday_utc", return_value="2026-07-17"),
            patch("app.services.pricing_signals.rollup_daily_signals", new_callable=AsyncMock, return_value=5) as mock_rollup,
            patch("app.services.pricing_signals.flag_suspicious_signals", new_callable=AsyncMock, return_value=1) as mock_flag,
        ):
            result = _run(run_daily_rollup_if_due(db_mock, redis_mock))

        assert result == 5
        mock_rollup.assert_awaited_once_with(db_mock, redis_mock, target_date="2026-07-17")
        mock_flag.assert_awaited_once_with(db_mock, target_date="2026-07-17")
        redis_mock.set.assert_awaited_once_with(Keys.last_rollup_date(), "2026-07-17")

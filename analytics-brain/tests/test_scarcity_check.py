"""Proactive scarcity check — mechanism 3 of the swarm coordination plan.
Pure functions first (no I/O), then the dedup guard (mocked redis)."""
from unittest.mock import AsyncMock

import pytest

from app.services.store_review import (
    LOW_STOCK_THRESHOLD,
    scarcity_signal_holds,
    find_matching_search_insight,
    format_scarcity_description,
    should_check_scarcity,
    mark_scarcity_checked,
)


class TestScarcitySignalHolds:
    def test_low_stock_and_high_demand_holds(self):
        assert scarcity_signal_holds(stock=3, recent_views=25, low_stock_threshold=5, demand_threshold=20) is True

    def test_low_stock_alone_does_not_hold(self):
        assert scarcity_signal_holds(stock=3, recent_views=5, low_stock_threshold=5, demand_threshold=20) is False

    def test_high_demand_alone_does_not_hold(self):
        assert scarcity_signal_holds(stock=50, recent_views=25, low_stock_threshold=5, demand_threshold=20) is False

    def test_neither_holds(self):
        assert scarcity_signal_holds(stock=50, recent_views=2, low_stock_threshold=5, demand_threshold=20) is False

    def test_exact_threshold_boundaries_are_inclusive(self):
        assert scarcity_signal_holds(stock=5, recent_views=20, low_stock_threshold=5, demand_threshold=20) is True


class TestFindMatchingSearchInsight:
    def test_substring_match_hits(self):
        insights = [{"label": "iphone", "count": 15, "query": "iphone", "matched": True, "last_at": 0}]
        result = find_matching_search_insight("iPhone 15 Pro Case", insights)
        assert result is not None
        assert result["label"] == "iphone"

    def test_no_match_returns_none(self):
        insights = [{"label": "skateboard", "count": 1, "query": "skateboard", "matched": False, "last_at": 0}]
        assert find_matching_search_insight("iPhone 15 Pro Case", insights) is None

    def test_empty_insights_returns_none(self):
        assert find_matching_search_insight("iPhone 15 Pro Case", []) is None


class TestFormatScarcityDescription:
    def test_leads_with_view_count_not_product_name(self):
        # decision_engine._extract_count() greps the first \d+ for the
        # grounded GMV estimate — a digit from the product name must never
        # come first, same reasoning as store_review.format_review_description.
        desc = format_scarcity_description("AirPods 2", stock=3, recent_views=25, search_insight=None)
        assert desc.startswith("Scarcity signal: 25 recent views")

    def test_includes_search_demand_note_when_present(self):
        insight = {"label": "airpods", "count": 8, "query": "airpods", "matched": True, "last_at": 0}
        desc = format_scarcity_description("AirPods 2", stock=3, recent_views=25, search_insight=insight)
        assert "search demand also present (8x)" in desc

    def test_omits_search_demand_note_when_absent(self):
        desc = format_scarcity_description("AirPods 2", stock=3, recent_views=25, search_insight=None)
        assert "search demand" not in desc


@pytest.mark.asyncio
class TestScarcityDedupGuard:
    async def test_should_check_true_when_not_yet_checked_today(self):
        redis = AsyncMock()
        redis.exists.return_value = 0
        assert await should_check_scarcity("p1", redis) is True

    async def test_should_check_false_when_already_checked_today(self):
        redis = AsyncMock()
        redis.exists.return_value = 1
        assert await should_check_scarcity("p1", redis) is False

    async def test_mark_checked_sets_a_key_with_a_ttl(self):
        redis = AsyncMock()
        await mark_scarcity_checked("p1", redis)
        redis.set.assert_awaited_once()
        _args, kwargs = redis.set.call_args
        assert kwargs.get("ex") is not None

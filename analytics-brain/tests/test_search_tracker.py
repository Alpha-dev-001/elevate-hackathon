import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.search_tracker import slugify_query, record_search, list_search_insights, MIN_QUERY_LENGTH


def _run(coro):
    return asyncio.run(coro)


def _mock_merchant(search_queries=None):
    m = MagicMock()
    m.id = "m1"
    m.search_queries = search_queries or {}
    return m


class TestSlugifyQuery:
    def test_collides_repeats(self):
        assert slugify_query("Winter Boots") == "winter-boots"
        assert slugify_query("winter_boots!!") == "winter-boots"
        assert slugify_query("  Winter   Boots  ") == "winter-boots"

    def test_empty_returns_placeholder(self):
        assert slugify_query("") == "unknown-query"


class TestRecordSearch:
    def test_short_query_not_recorded(self):
        db = AsyncMock()
        assert _run(record_search("m1", "a", False, db)) is None
        assert MIN_QUERY_LENGTH == 2
        db.get.assert_not_awaited()

    def test_unknown_merchant_returns_none(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        assert _run(record_search("missing", "boots", True, db)) is None

    def test_first_search_recorded_with_count_one(self):
        merchant = _mock_merchant()
        db = AsyncMock()
        db.get = AsyncMock(return_value=merchant)
        result = _run(record_search("m1", "winter boots", True, db))
        assert result == {"query": "winter-boots", "label": "winter boots", "count": 1, "matched": True}
        db.commit.assert_awaited_once()

    def test_repeat_search_increments_count(self):
        merchant = _mock_merchant({"winter-boots": {"count": 3, "query": "winter boots", "matched": True}})
        db = AsyncMock()
        db.get = AsyncMock(return_value=merchant)
        result = _run(record_search("m1", "winter boots", True, db))
        assert result["count"] == 4

    def test_unmatched_query_flagged(self):
        merchant = _mock_merchant()
        db = AsyncMock()
        db.get = AsyncMock(return_value=merchant)
        result = _run(record_search("m1", "leather sandals", False, db))
        assert result["matched"] is False

    def test_once_matched_stays_matched(self):
        """A temporarily out-of-stock item shouldn't get permanently
        mislabeled as unmet demand just because of one later miss."""
        merchant = _mock_merchant({"boots": {"count": 5, "query": "boots", "matched": True}})
        db = AsyncMock()
        db.get = AsyncMock(return_value=merchant)
        result = _run(record_search("m1", "boots", False, db))
        assert result["matched"] is True


class TestListSearchInsights:
    def test_empty_when_no_searches(self):
        merchant = _mock_merchant()
        db = AsyncMock()
        db.get = AsyncMock(return_value=merchant)
        assert _run(list_search_insights("m1", db)) == []

    def test_sorted_by_count_descending(self):
        merchant = _mock_merchant({
            "sandals": {"count": 2, "query": "sandals", "matched": True},
            "raincoat": {"count": 9, "query": "raincoat", "matched": False},
        })
        db = AsyncMock()
        db.get = AsyncMock(return_value=merchant)
        out = _run(list_search_insights("m1", db))
        assert [x["query"] for x in out] == ["raincoat", "sandals"]

    def test_unmatched_flag_surfaced(self):
        merchant = _mock_merchant({"raincoat": {"count": 9, "query": "raincoat", "matched": False}})
        db = AsyncMock()
        db.get = AsyncMock(return_value=merchant)
        out = _run(list_search_insights("m1", db))
        assert out[0]["matched"] is False

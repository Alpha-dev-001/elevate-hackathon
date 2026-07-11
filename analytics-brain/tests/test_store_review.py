"""Tests for store_review's pure selection logic — the proactive review
trigger. Mirrors test_behavior_tracker.py's approach: test the decision
rule directly, not through Redis/Postgres (that's covered by bench_live.py
/ live integration scripts, per this repo's existing convention)."""
from app.services.store_review import (
    extract_ordered_product_ids,
    pick_underperformer,
    format_review_description,
)


class TestExtractOrderedProductIds:
    def test_empty_orders(self):
        assert extract_ordered_product_ids([]) == set()

    def test_none_items(self):
        """An order with a null/missing items blob shouldn't crash the scan."""
        assert extract_ordered_product_ids([None, []]) == set()

    def test_collects_ids_across_orders(self):
        orders = [
            [{"product_id": "p1", "qty": 1}, {"product_id": "p2", "qty": 2}],
            [{"product_id": "p3", "qty": 1}],
        ]
        assert extract_ordered_product_ids(orders) == {"p1", "p2", "p3"}

    def test_dedupes_repeated_ids(self):
        orders = [[{"product_id": "p1"}], [{"product_id": "p1"}]]
        assert extract_ordered_product_ids(orders) == {"p1"}

    def test_ignores_malformed_items(self):
        """A non-dict item or a dict missing product_id must not crash or
        get silently counted as an order."""
        orders = [["not-a-dict", {"no_product_id": True}, {"product_id": "p1"}]]
        assert extract_ordered_product_ids(orders) == {"p1"}


class TestPickUnderperformer:
    def test_no_products_returns_none(self):
        assert pick_underperformer([], set(), min_views=5) is None

    def test_below_min_views_returns_none(self):
        assert pick_underperformer([("p1", 3.0)], set(), min_views=5) is None

    def test_picks_highest_viewed_unordered_product(self):
        """Sorted descending — the first one to clear both bars wins."""
        velocity = [("p1", 40.0), ("p2", 20.0), ("p3", 10.0)]
        assert pick_underperformer(velocity, ordered_product_ids=set(), min_views=5) == "p1"

    def test_skips_products_with_real_orders(self):
        velocity = [("p1", 40.0), ("p2", 20.0)]
        assert pick_underperformer(velocity, ordered_product_ids={"p1"}, min_views=5) == "p2"

    def test_all_ordered_returns_none(self):
        velocity = [("p1", 40.0), ("p2", 20.0)]
        assert pick_underperformer(velocity, ordered_product_ids={"p1", "p2"}, min_views=5) is None

    def test_stops_at_first_below_threshold(self):
        """Descending list: once one candidate misses min_views, nothing
        after it can qualify — pick_underperformer must not keep scanning
        past it even if a later (impossible) entry would otherwise match."""
        velocity = [("p1", 40.0), ("p2", 3.0)]
        # p1 already has an order, p2 is below min_views — expect None, not p2.
        assert pick_underperformer(velocity, ordered_product_ids={"p1"}, min_views=5) is None

    def test_exactly_at_min_views_qualifies(self):
        assert pick_underperformer([("p1", 5.0)], set(), min_views=5) == "p1"


class TestFormatReviewDescription:
    def test_view_count_leads_the_sentence(self):
        """decision_engine._extract_count() greps the first \\d+ in the
        description for the grounded GMV estimate — the view count must
        come before the product name so a numeric product name (e.g.
        'AirPods 2') can never be mistaken for the view count."""
        desc = format_review_description("AirPods 2", 12, window_hours=24)
        # "Store review: 12 views..." — the count must be the first digit
        # token, ahead of the "2" in the product name.
        import re
        m = re.search(r"\d+", desc)
        assert m.group() == "12"

    def test_includes_product_name_and_window(self):
        desc = format_review_description("Leather Slides", 8, window_hours=24)
        assert "Leather Slides" in desc
        assert "24h" in desc
        assert "0 orders" in desc

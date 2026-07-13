"""Tests for product_featuring's pure scoring logic — the 6th autopilot
trigger. Same convention as test_store_review.py: test the pure functions
directly. The async I/O wrapper (evaluate_new_products) has no dedicated
unit test, matching store_review.py's own find_underperformer/
run_store_review precedent — covered by manual/live verification instead."""
from app.services.product_featuring import score_candidates, pick_best_candidate


class TestScoreCandidates:
    def test_empty_input_returns_empty(self):
        assert score_candidates([], {}) == []

    def test_category_with_no_stats_is_skipped(self):
        """A brand-new category with zero order history has nothing to
        ground the score in — not comparable, must not be scored."""
        candidates = [("p1", "New Hat", 30.0, "hats")]
        assert score_candidates(candidates, {}) == []

    def test_category_below_min_orders_is_skipped(self):
        candidates = [("p1", "New Hat", 30.0, "hats")]
        category_stats = {"hats": (25.0, 0)}  # 0 recent orders — not proven
        assert score_candidates(candidates, category_stats) == []

    def test_scores_comparable_candidate(self):
        candidates = [("p1", "New Slides", 40.0, "footwear")]
        category_stats = {"footwear": (40.0, 5)}  # price matches avg exactly
        scored = score_candidates(candidates, category_stats)
        assert len(scored) == 1
        product_id, score, comparison = scored[0]
        assert product_id == "p1"
        assert score == 5.0  # order_count(5) - price_penalty(0, exact match)
        assert "New Slides" in comparison
        assert "footwear" in comparison

    def test_price_far_from_average_is_penalized(self):
        """A $400 item dropped into a $20-average category is a mismatch,
        however many orders that category has — the penalty should pull
        its score below a well-matched candidate in the same category."""
        far = [("p1", "Luxury Item", 400.0, "budget")]
        close = [("p2", "Budget Item", 22.0, "budget")]
        category_stats = {"budget": (20.0, 10)}
        far_score = score_candidates(far, category_stats)[0][1]
        close_score = score_candidates(close, category_stats)[0][1]
        assert close_score > far_score

    def test_multiple_candidates_all_scored(self):
        candidates = [
            ("p1", "Item A", 40.0, "footwear"),
            ("p2", "Item B", 20.0, "hats"),
        ]
        category_stats = {"footwear": (40.0, 3), "hats": (20.0, 1)}
        scored = score_candidates(candidates, category_stats)
        assert len(scored) == 2


class TestPickBestCandidate:
    def test_empty_returns_none(self):
        assert pick_best_candidate([]) is None

    def test_picks_highest_score(self):
        scored = [
            ("p1", 2.0, "comparison for p1"),
            ("p2", 5.0, "comparison for p2"),
            ("p3", 1.0, "comparison for p3"),
        ]
        assert pick_best_candidate(scored) == ("p2", "comparison for p2")

    def test_single_candidate(self):
        scored = [("p1", 3.0, "only one")]
        assert pick_best_candidate(scored) == ("p1", "only one")

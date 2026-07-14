from app.services.pricing_cycle import is_price_rebalance_eligible, select_comparable_product


class TestIsPriceRebalanceEligible:
    def test_below_both_thresholds_not_eligible(self):
        assert is_price_rebalance_eligible(history_row_count=1, purchase_count=0) is False

    def test_three_days_history_eligible_even_with_zero_purchases(self):
        assert is_price_rebalance_eligible(history_row_count=3, purchase_count=0) is True

    def test_one_purchase_eligible_even_with_zero_history_rows(self):
        assert is_price_rebalance_eligible(history_row_count=0, purchase_count=1) is True

    def test_two_days_and_zero_purchases_not_eligible(self):
        assert is_price_rebalance_eligible(history_row_count=2, purchase_count=0) is False


class TestSelectComparableProduct:
    def _candidate(self, product_id, category="shoes", baseline_price=20.0, history_row_count=5, purchase_count=2):
        return {
            "product_id": product_id, "category": category,
            "baseline_price": baseline_price,
            "history_row_count": history_row_count, "purchase_count": purchase_count,
        }

    def test_no_candidates_returns_none(self):
        assert select_comparable_product(20.0, "shoes", []) is None

    def test_same_category_within_band_and_eligible_selected(self):
        candidates = [self._candidate("p2", baseline_price=22.0)]
        assert select_comparable_product(20.0, "shoes", candidates) == "p2"

    def test_different_category_excluded(self):
        candidates = [self._candidate("p2", category="hats", baseline_price=20.0)]
        assert select_comparable_product(20.0, "shoes", candidates) is None

    def test_outside_thirty_percent_band_excluded(self):
        # 20 * 1.30 = 26.0 is the edge; 27.0 is outside it.
        candidates = [self._candidate("p2", baseline_price=27.0)]
        assert select_comparable_product(20.0, "shoes", candidates) is None

    def test_ineligible_candidate_excluded_even_if_price_matches(self):
        # A candidate that's itself cold-start (not yet proven) can't donate history.
        candidates = [self._candidate("p2", baseline_price=20.0, history_row_count=1, purchase_count=0)]
        assert select_comparable_product(20.0, "shoes", candidates) is None

    def test_closest_baseline_price_wins_among_multiple_valid(self):
        candidates = [
            self._candidate("p2", baseline_price=25.0),
            self._candidate("p3", baseline_price=21.0),
        ]
        assert select_comparable_product(20.0, "shoes", candidates) == "p3"

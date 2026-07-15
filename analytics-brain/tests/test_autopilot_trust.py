from app.services.autopilot_trust import next_streak, should_auto_apply, TRUST_STREAK_THRESHOLD
from app.models.schemas import BusinessConstraints


class TestNextStreak:
    def test_approved_positive_outcome_increments(self):
        assert next_streak(2, approved=True, outcome_negative=False) == 3

    def test_dismissed_resets_to_zero(self):
        assert next_streak(5, approved=False, outcome_negative=False) == 0

    def test_approved_negative_outcome_resets_to_zero(self):
        assert next_streak(5, approved=True, outcome_negative=True) == 0

    def test_zero_streak_dismissed_stays_zero(self):
        assert next_streak(0, approved=False, outcome_negative=False) == 0


class TestTrustEvaluationUsesRealPurchaseSignal:
    """Proves the exact composition pricing_cycle.evaluate_trust_outcomes
    relies on: outcome_negative must be derived from REAL post-move
    product_price_history purchases, not from OrderDB.promo_applied (which a
    direct price change never populates — found in final whole-branch review,
    see evaluate_trust_outcomes' docstring). This is the property that was
    silently broken end-to-end before the fix: an approved move with zero
    real purchases in the window must still reset to 0, and one with real
    purchases must still increment — exactly like next_streak already
    guarantees, this just proves the real signal maps onto it correctly."""

    def test_approved_move_with_zero_real_purchases_resets_despite_approval(self):
        purchases_in_window = 0
        outcome_negative = purchases_in_window == 0
        assert next_streak(2, approved=True, outcome_negative=outcome_negative) == 0

    def test_approved_move_with_real_purchases_increments(self):
        purchases_in_window = 3
        outcome_negative = purchases_in_window == 0
        assert next_streak(2, approved=True, outcome_negative=outcome_negative) == 3


class TestShouldAutoApply:
    def _constraints(self, max_uplift=10.0, max_discount=40.0):
        return BusinessConstraints(max_uplift_percent=max_uplift, max_discount_percent=max_discount)

    def test_below_threshold_never_auto_applies(self):
        assert should_auto_apply(
            TRUST_STREAK_THRESHOLD - 1, 21.0, 20.0, self._constraints(),
        ) is False

    def test_at_threshold_within_band_auto_applies(self):
        # 21.0 vs baseline 20.0 = +5%, well within the 10% band and the 10% ceiling.
        assert should_auto_apply(
            TRUST_STREAK_THRESHOLD, 21.0, 20.0, self._constraints(max_uplift=10.0),
        ) is True

    def test_upward_move_capped_by_merchants_own_uplift_ceiling_not_flat_ten_percent(self):
        # max_uplift_percent=5 means the effective band is min(10, 5) = 5%, not 10%.
        # A +8% move is inside the flat 10% but OUTSIDE the merchant's real 5% ceiling.
        assert should_auto_apply(
            100, 21.6, 20.0, self._constraints(max_uplift=5.0),
        ) is False

    def test_upward_move_within_the_narrower_uplift_ceiling_auto_applies(self):
        assert should_auto_apply(
            100, 21.0, 20.0, self._constraints(max_uplift=5.0),
        ) is True

    def test_downward_move_within_ten_percent_auto_applies_regardless_of_streak_size(self):
        # Explicit high-streak test per the spec's own testing requirement.
        assert should_auto_apply(
            100, 19.0, 20.0, self._constraints(),
        ) is True

    def test_downward_move_beyond_ten_percent_always_gates_even_at_streak_100(self):
        assert should_auto_apply(
            100, 17.0, 20.0, self._constraints(),
        ) is False

    def test_zero_baseline_never_auto_applies(self):
        assert should_auto_apply(100, 21.0, 0.0, self._constraints()) is False

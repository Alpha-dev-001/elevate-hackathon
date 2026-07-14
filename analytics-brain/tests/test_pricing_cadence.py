from app.services.pricing_cycle import (
    next_check_decision,
    PRICE_REVIEW_INTERVAL_SECONDS,
    PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS,
    PRICE_REVIEW_ESCALATION_DECAY_TICKS,
)


class TestNextCheckDecision:
    def test_quiet_product_with_no_streak_stays_daily(self):
        streak, interval = next_check_decision(0, escalated_this_tick=False)
        assert streak == 0
        assert interval == PRICE_REVIEW_INTERVAL_SECONDS

    def test_fresh_anomaly_escalates_to_hourly_and_starts_streak_at_one(self):
        streak, interval = next_check_decision(0, escalated_this_tick=True)
        assert streak == 1
        assert interval == PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS

    def test_fresh_anomaly_resets_an_existing_decaying_streak_to_one(self):
        streak, interval = next_check_decision(2, escalated_this_tick=True)
        assert streak == 1
        assert interval == PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS

    def test_quiet_tick_during_escalation_continues_counting(self):
        streak, interval = next_check_decision(1, escalated_this_tick=False)
        assert streak == 2
        assert interval == PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS

    def test_third_consecutive_quiet_tick_decays_back_to_daily(self):
        # PRICE_REVIEW_ESCALATION_DECAY_TICKS == 3: streak 2 -> 3 hits decay.
        streak, interval = next_check_decision(PRICE_REVIEW_ESCALATION_DECAY_TICKS - 1, escalated_this_tick=False)
        assert streak == 0
        assert interval == PRICE_REVIEW_INTERVAL_SECONDS

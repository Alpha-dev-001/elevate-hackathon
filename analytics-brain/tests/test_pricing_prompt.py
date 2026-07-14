from app.services.pricing_cycle import (
    format_history_summary,
    compute_magnitude,
    build_revealed_preference_summary,
    compose_pricing_prompt,
)


class TestFormatHistorySummary:
    def test_empty_rows(self):
        assert format_history_summary([]) == "no trusted history yet"

    def test_excludes_suspect_days(self):
        rows = [
            {"date": "2026-07-10", "views": 10, "cart_adds": 2, "purchases": 1, "price_active": 20.0, "signal_quality": "normal"},
            {"date": "2026-07-11", "views": 500, "cart_adds": 0, "purchases": 0, "price_active": 20.0, "signal_quality": "suspect"},
        ]
        summary = format_history_summary(rows)
        assert "2026-07-10" in summary
        assert "2026-07-11" not in summary

    def test_all_suspect_returns_no_trusted_history(self):
        rows = [{"date": "2026-07-11", "views": 500, "cart_adds": 0, "purchases": 0, "price_active": 20.0, "signal_quality": "suspect"}]
        assert format_history_summary(rows) == "no trusted history yet"


class TestComputeMagnitude:
    def test_discount_bearing_action(self):
        assert compute_magnitude("flash_sale", {"discount_percent": 15.0}, None) == 15.0

    def test_price_rebalance_computes_percent_from_baseline(self):
        mag = compute_magnitude("price_rebalance", {"new_price": 22.0}, 20.0)
        assert mag == 10.0

    def test_price_rebalance_without_baseline_returns_none(self):
        assert compute_magnitude("price_rebalance", {"new_price": 22.0}, None) is None

    def test_unrecognized_shape_returns_none(self):
        assert compute_magnitude("layout_morph", {"new_grid": "grid-3col"}, None) is None


class TestBuildRevealedPreferenceSummary:
    def test_no_actions_returns_empty_string(self):
        assert build_revealed_preference_summary([]) == ""

    def test_approved_and_dismissed_both_present(self):
        actions = [
            {"action_type": "flash_sale", "status": "executed", "payload": {"discount_percent": 25.0}},
            {"action_type": "flash_sale", "status": "dismissed", "payload": {"discount_percent": 35.0}},
        ]
        summary = build_revealed_preference_summary(actions)
        assert "25" in summary
        assert "35" in summary

    def test_pending_actions_ignored(self):
        actions = [{"action_type": "flash_sale", "status": "pending", "payload": {"discount_percent": 25.0}}]
        assert build_revealed_preference_summary(actions) == ""


class TestComposePricingPrompt:
    def test_includes_all_required_fields(self):
        prompt = compose_pricing_prompt(
            store_name="Emma Fashion", mood="minimal", brand_voice="playful",
            product_name="Leather Slides", baseline_price=20.0, current_price=20.0,
            cost_price=10.0, history_summary="2026-07-10: 10 views, 2 cart-adds, 1 purchases at $20.00",
        )
        assert "Emma Fashion" in prompt
        assert "Leather Slides" in prompt
        assert "$20.00" in prompt
        assert "propose_price_rebalance" in prompt

    def test_comparable_block_only_present_when_given(self):
        without = compose_pricing_prompt(
            store_name="S", mood="m", brand_voice="v", product_name="P",
            baseline_price=20.0, current_price=20.0, cost_price=10.0, history_summary="h",
        )
        with_comp = compose_pricing_prompt(
            store_name="S", mood="m", brand_voice="v", product_name="P",
            baseline_price=20.0, current_price=20.0, cost_price=10.0, history_summary="h",
            comparable_summary="Similar Product X: sustained +8% with no drop in conversion",
        )
        assert "Similar Product X" not in without
        assert "Similar Product X" in with_comp

from app.services.pricing_cycle import should_revert, compute_reversion_price


class TestShouldRevert:
    def test_views_with_zero_purchases_is_engagement_without_conversion(self):
        assert should_revert(views_after=15, cart_adds_after=0, purchases_after=0) is True

    def test_cart_adds_with_zero_purchases_is_engagement_without_conversion(self):
        assert should_revert(views_after=0, cart_adds_after=3, purchases_after=0) is True

    def test_purchases_present_never_reverts(self):
        assert should_revert(views_after=15, cart_adds_after=3, purchases_after=1) is False

    def test_zero_everything_is_low_traffic_not_engagement_without_conversion(self):
        # No clicks at all is a distinct signal from "click but no buy" —
        # per the spec's explicit "meaningful specifically" distinction.
        assert should_revert(views_after=0, cart_adds_after=0, purchases_after=0) is False


class TestComputeReversionPrice:
    def test_halves_the_remaining_gap_moving_down(self):
        # current 22.0, baseline 20.0 -> gap -2.0 -> half is -1.0 -> 21.0
        assert compute_reversion_price(22.0, 20.0) == 21.0

    def test_halves_the_remaining_gap_moving_up(self):
        # current 16.0, baseline 20.0 -> gap +4.0 -> half is +2.0 -> 18.0
        assert compute_reversion_price(16.0, 20.0) == 18.0

    def test_repeated_halving_converges_toward_baseline(self):
        # Halving a currency amount rounded to cents can plateau at exactly a
        # 1-cent gap forever (0.005 rounds to 0.01) rather than reaching 0 —
        # correct real-world behavior for a price. Tolerance is slightly above
        # one cent to also clear float representation noise (20.01 - 20.0 is
        # not bit-exact 0.01 in IEEE 754).
        price = 22.0
        for _ in range(10):
            price = compute_reversion_price(price, 20.0)
        assert abs(price - 20.0) < 0.015

    def test_already_at_baseline_stays_there(self):
        assert compute_reversion_price(20.0, 20.0) == 20.0

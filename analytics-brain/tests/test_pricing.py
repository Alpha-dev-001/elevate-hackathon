from app.services.pricing import effective_price
from app.models.schemas import Promo


def _promo(discount_percent, expires_at=99999999999999):
    return Promo(
        id="promo1", product_id="p1", discount_percent=discount_percent,
        label="Test Sale", expires_at=expires_at, triggered_by="auto",
    )


class TestEffectivePriceBaseline:
    def test_no_promo_no_baseline_unchanged_behavior(self):
        price, compare_at, label = effective_price(20.0, None)
        assert (price, compare_at, label) == (20.0, None, None)

    def test_price_below_baseline_gets_strike_through(self):
        price, compare_at, label = effective_price(18.0, None, baseline_price=20.0)
        assert price == 18.0
        assert compare_at == 20.0
        assert label is None

    def test_price_above_baseline_stays_plain(self):
        price, compare_at, label = effective_price(22.0, None, baseline_price=20.0)
        assert price == 22.0
        assert compare_at is None
        assert label is None

    def test_price_at_baseline_stays_plain(self):
        price, compare_at, label = effective_price(20.0, None, baseline_price=20.0)
        assert compare_at is None

    def test_active_promo_wins_over_baseline_comparison(self):
        # Live price already moved above baseline (24.0 vs baseline 20.0), but
        # an active 25% promo still applies its OWN discount/compare_at off
        # the live price — baseline is irrelevant once a promo is active.
        price, compare_at, label = effective_price(24.0, _promo(25.0), baseline_price=20.0)
        assert price == 18.0  # 24 * 0.75
        assert compare_at == 24.0  # the live price, not the baseline
        assert label == "Test Sale"

    def test_existing_promo_only_behavior_unaffected_when_baseline_omitted(self):
        # Every existing caller that doesn't pass baseline_price at all keeps
        # today's exact behavior (regression check).
        price, compare_at, label = effective_price(20.0, _promo(10.0))
        assert price == 18.0
        assert compare_at == 20.0
        assert label == "Test Sale"

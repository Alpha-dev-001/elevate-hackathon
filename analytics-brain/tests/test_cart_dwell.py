from app.services.cart_dwell import is_dwelling, CART_DWELL_MINUTES


class TestIsDwelling:
    def test_empty_cart_never_dwells(self):
        now = 1_000_000_000
        assert is_dwelling(now - CART_DWELL_MINUTES * 60_000 - 1, has_items=False, now_ms=now) is False

    def test_recently_touched_cart_is_not_dwelling(self):
        now = 1_000_000_000
        assert is_dwelling(now - 60_000, has_items=True, now_ms=now) is False  # touched 1 min ago

    def test_stale_cart_is_dwelling(self):
        now = 1_000_000_000
        stale_ms = (CART_DWELL_MINUTES + 1) * 60_000
        assert is_dwelling(now - stale_ms, has_items=True, now_ms=now) is True

    def test_exactly_at_threshold_is_dwelling(self):
        now = 1_000_000_000
        assert is_dwelling(now - CART_DWELL_MINUTES * 60_000, has_items=True, now_ms=now) is True

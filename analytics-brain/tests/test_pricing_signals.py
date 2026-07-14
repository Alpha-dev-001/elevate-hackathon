from app.services.pricing_signals import count_signals_for_product


def test_counts_only_matching_product():
    events = [
        {"product_id": "p1", "event_type": "view"},
        {"product_id": "p2", "event_type": "view"},
        {"product_id": "p1", "event_type": "add_to_cart"},
        {"product_id": "p1", "event_type": "purchase"},
        {"product_id": "p1", "event_type": "view"},
    ]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 2, "cart_adds": 1}


def test_no_matching_events_returns_zeros():
    events = [{"product_id": "p2", "event_type": "view"}]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 0, "cart_adds": 0}


def test_ignores_non_counted_event_types():
    events = [
        {"product_id": "p1", "event_type": "hover"},
        {"product_id": "p1", "event_type": "abandon"},
        {"product_id": "p1", "event_type": "purchase"},
    ]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 0, "cart_adds": 0}


from app.services.pricing_signals import is_suspicious


def test_high_views_near_zero_cart_adds_is_suspicious():
    # 5x trailing average, cart_adds effectively zero relative to that view count.
    assert is_suspicious(today_views=100, today_cart_adds=0, trailing_avg_views=20.0) is True


def test_high_views_with_real_cart_adds_is_not_suspicious():
    # Same view spike, but genuine engagement (cart_adds proportional to views).
    assert is_suspicious(today_views=100, today_cart_adds=15, trailing_avg_views=20.0) is False


def test_normal_day_is_not_suspicious():
    assert is_suspicious(today_views=22, today_cart_adds=3, trailing_avg_views=20.0) is False


def test_zero_trailing_average_never_flags():
    # No baseline to compare against (brand-new product) — can't call it
    # suspicious with nothing to be anomalous relative to.
    assert is_suspicious(today_views=50, today_cart_adds=0, trailing_avg_views=0.0) is False

from app.services.pricing_signals import count_signals_for_product


def test_counts_only_matching_product():
    events = [
        {"product_id": "p1", "event_type": "view"},
        {"product_id": "p2", "event_type": "view"},
        {"product_id": "p1", "event_type": "cart_add"},
        {"product_id": "p1", "event_type": "purchase"},
        {"product_id": "p1", "event_type": "view"},
    ]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 2, "cart_adds": 1, "purchases": 1}


def test_no_matching_events_returns_zeros():
    events = [{"product_id": "p2", "event_type": "view"}]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 0, "cart_adds": 0, "purchases": 0}


def test_ignores_non_counted_event_types():
    events = [
        {"product_id": "p1", "event_type": "hover"},
        {"product_id": "p1", "event_type": "abandon"},
    ]
    counts = count_signals_for_product(events, "p1")
    assert counts == {"views": 0, "cart_adds": 0, "purchases": 0}

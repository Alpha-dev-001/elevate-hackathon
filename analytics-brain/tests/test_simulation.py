"""Demo/test simulation suite — pure event-generation core.

The suite drives synthetic customer activity through the REAL pipeline (no mocks);
these tests pin the pure part: given a scenario, real product ids, and a customer
count, produce a fanned event list that is GUARANTEED to cross the scenario's
anomaly threshold even for a small crowd. The async orchestration that pushes
these through record_event → anomaly detection → run_decision_cycle is thin glue
over already-tested services.
"""
import pytest

from app.services.simulation import build_events, SCENARIOS


PRODUCTS = ["p-alpha", "p-beta", "p-gamma"]


def _count(events, etype, pid=None):
    return sum(1 for e in events if e["event_type"] == etype and (pid is None or e["product_id"] == pid))


def _sessions(events):
    return {e["session_id"] for e in events}


def test_velocity_crosses_the_20_view_threshold_on_one_product():
    events = build_events("velocity_spike", PRODUCTS, customers=8)
    # The target (first) product must own >= 20 views so it's the spiking one.
    assert _count(events, "view", PRODUCTS[0]) >= 20


def test_abandon_crosses_the_5_abandon_threshold():
    events = build_events("cart_abandon_surge", PRODUCTS, customers=3)
    assert _count(events, "abandon", PRODUCTS[0]) >= 5


def test_small_customer_count_still_crosses_threshold():
    # Even 1 simulated customer must produce a firing scenario (floored).
    assert _count(build_events("velocity_spike", PRODUCTS, 1), "view", PRODUCTS[0]) >= 20
    assert _count(build_events("cart_abandon_surge", PRODUCTS, 1), "abandon", PRODUCTS[0]) >= 5


def test_events_fan_across_at_most_customers_sessions():
    events = build_events("velocity_spike", PRODUCTS, customers=6)
    assert 1 <= len(_sessions(events)) <= 6


def test_dwell_leaves_carts_without_abandon_or_purchase():
    events = build_events("cart_dwell", PRODUCTS, customers=4)
    assert _count(events, "cart_add", PRODUCTS[0]) >= 1
    assert _count(events, "abandon") == 0
    assert _count(events, "purchase") == 0


def test_every_event_has_the_required_shape():
    for name in SCENARIOS:
        for e in build_events(name, PRODUCTS, customers=5):
            assert set(e) >= {"event_type", "product_id", "session_id", "delay"}
            assert e["product_id"] in PRODUCTS


def test_unknown_scenario_raises():
    with pytest.raises(ValueError):
        build_events("not_a_scenario", PRODUCTS, customers=5)


def test_empty_product_list_raises():
    with pytest.raises(ValueError):
        build_events("velocity_spike", [], customers=5)

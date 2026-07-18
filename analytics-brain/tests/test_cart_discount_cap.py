"""Double-discount clamp — the order-level recovery/dwell discount (applied on top
of a line whose price may already carry a product-level flash_sale) must never push
a line below its cost. This caps the *combination* at the point the cart price is
set, so the customer never sees — or is charged — a below-cost stacked total.
"""
from app.services.cart import cap_discount_for_cost


class _L:
    def __init__(self, unit_price, cost_price=None):
        self.unit_price = unit_price
        self.cost_price = cost_price


def test_discount_within_margin_is_unchanged():
    # 10% off a $10 line costing $6 → $9 final, well above cost.
    assert cap_discount_for_cost([_L(10.0, 6.0)], 10.0) == 10.0


def test_discount_clamped_so_line_never_sells_below_cost():
    # 50% off $10 costing $6 → $5 < cost; the largest safe order discount is 40%.
    assert cap_discount_for_cost([_L(10.0, 6.0)], 50.0) == 40.0


def test_tightest_line_in_the_cart_wins():
    # line A tolerates 40%, line B (cost 8) tolerates 20% → the cart caps at 20%.
    assert cap_discount_for_cost([_L(10.0, 6.0), _L(10.0, 8.0)], 50.0) == 20.0


def test_zero_request_stays_zero():
    assert cap_discount_for_cost([_L(10.0, 6.0)], 0.0) == 0.0


def test_line_without_a_cost_snapshot_is_skipped():
    # A legacy cart line has no cost snapshot — can't verify, so don't over-clamp.
    assert cap_discount_for_cost([_L(10.0, None)], 30.0) == 30.0


def test_a_line_already_at_or_below_cost_forbids_any_further_discount():
    assert cap_discount_for_cost([_L(5.0, 6.0)], 20.0) == 0.0


def test_no_items_returns_the_request():
    assert cap_discount_for_cost([], 25.0) == 25.0

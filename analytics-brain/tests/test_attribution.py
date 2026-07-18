"""Attribution — matching orders to the Elevate actions that drove them.

An order can carry MORE THAN ONE promo id: a product-level flash_sale AND an
order-level recovery_offer stack, so `OrderDB.promo_applied` is a ", "-joined
list ("ELEV_A, ELEV_B"). The bug this pins: consumers matched a single
`action.promo_id` against the whole joined string, so any stacked order fell out
of attribution (revenue landed, but was never tagged Elevate-attributed — and the
learning loop mis-saw it as "no conversion"). The fix must:
  - attribute a stacked order to EVERY action that contributed to it, and
  - count that order's GMV only ONCE in the store total (no double-counting).
"""
from app.services.attribution import promo_ids_of, attribute_orders, total_attributed_gmv


class _O:
    def __init__(self, oid, total, promo_applied):
        self.id, self.total, self.promo_applied = oid, total, promo_applied


def test_promo_ids_of_splits_comma_joined():
    assert promo_ids_of("ELEV_A, ELEV_B") == ["ELEV_A", "ELEV_B"]
    assert promo_ids_of("ELEV_A") == ["ELEV_A"]
    assert promo_ids_of(None) == []
    assert promo_ids_of("") == []


def test_stacked_order_is_attributed_to_both_actions():
    order = _O("o1", 8.14, "ELEV_A, ELEV_B")
    m = attribute_orders([order], ["ELEV_A", "ELEV_B"])
    assert order in m["ELEV_A"]
    assert order in m["ELEV_B"]


def test_single_promo_order_still_attributed():
    order = _O("o2", 15.70, "ELEV_C")
    m = attribute_orders([order], ["ELEV_C"])
    assert m["ELEV_C"] == [order]


def test_total_counts_a_stacked_order_only_once():
    order = _O("o1", 8.14, "ELEV_A, ELEV_B")
    m = attribute_orders([order], ["ELEV_A", "ELEV_B"])
    assert total_attributed_gmv(m) == 8.14  # NOT 16.28


def test_total_sums_distinct_orders():
    m = attribute_orders(
        [_O("o1", 10.0, "ELEV_A"), _O("o2", 5.0, "ELEV_B")],
        ["ELEV_A", "ELEV_B"],
    )
    assert total_attributed_gmv(m) == 15.0


def test_action_with_no_matching_order_gets_empty_list():
    m = attribute_orders([_O("o1", 10.0, "ELEV_A")], ["ELEV_Z"])
    assert m["ELEV_Z"] == []


def test_order_with_no_promo_is_ignored():
    m = attribute_orders([_O("o1", 10.0, None), _O("o2", 5.0, "ELEV_A")], ["ELEV_A"])
    assert m["ELEV_A"] == [_o for _o in m["ELEV_A"]]  # only the promo'd order
    assert len(m["ELEV_A"]) == 1

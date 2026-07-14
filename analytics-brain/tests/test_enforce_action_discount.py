# analytics-brain/tests/test_enforce_action_discount.py
from app.services.interceptor import enforce_action_discount
from app.models.schemas import AgentActionType, BusinessConstraints

DEFAULT = BusinessConstraints(min_profit_margin_percent=20, max_discount_percent=40, min_price={})


def test_non_discount_action_passes_through_unchanged():
    args, msg, blocked = enforce_action_discount(
        AgentActionType.LAYOUT_MORPH, {"new_grid": "masonry-4col"},
        cost_price=10.0, price=20.0, constraints=DEFAULT,
    )
    assert args == {"new_grid": "masonry-4col"}
    assert msg == ""
    assert blocked is False


def test_within_ceiling_and_above_cost_passes_clean():
    args, msg, blocked = enforce_action_discount(
        AgentActionType.FLASH_SALE, {"product_id": "p1", "discount_percent": 10},
        cost_price=10.0, price=20.0, constraints=DEFAULT,
    )
    assert args["discount_percent"] == 10
    assert msg == ""
    assert blocked is False


def test_exceeds_ceiling_gets_clamped_with_message():
    args, msg, blocked = enforce_action_discount(
        AgentActionType.FLASH_SALE, {"product_id": "p1", "discount_percent": 60},
        cost_price=10.0, price=20.0, constraints=DEFAULT,
    )
    assert args["discount_percent"] == 40
    assert "40" in msg
    assert blocked is False


def test_even_ceiling_clamp_sells_below_cost_blocks():
    # base_price so low that even the 40% ceiling clamp still undercuts cost.
    args, msg, blocked = enforce_action_discount(
        AgentActionType.SCARCITY_PRICE, {"product_id": "p1", "discount_percent": 90},
        cost_price=15.0, price=20.0, constraints=DEFAULT,
    )
    assert blocked is True
    assert "below" in msg.lower() or "cost" in msg.lower()


def test_merchant_min_price_floor_overrides_percent_margin():
    # 20% margin floor on cost=10 is 12.0, but the merchant set an explicit
    # $18 floor for this product — that must win even though 12.0 would
    # otherwise "clear cost" under the plain enforce_discount check.
    constraints = BusinessConstraints(
        min_profit_margin_percent=20, max_discount_percent=40,
        min_price={"p1": 18.0},
    )
    args, msg, blocked = enforce_action_discount(
        AgentActionType.FLASH_SALE, {"product_id": "p1", "discount_percent": 40},
        cost_price=10.0, price=20.0, constraints=constraints, product_id="p1",
    )
    assert blocked is False
    # 40% off $20 = $12, below the $18 floor — must clamp to the floor, i.e. 10%.
    assert args["discount_percent"] == 10.0
    assert "18" in msg


def test_recovery_offer_is_ceiling_only_no_below_cost_check():
    args, msg, blocked = enforce_action_discount(
        AgentActionType.RECOVERY_OFFER, {"discount_percent": 90},
        cost_price=0.0, price=0.0, constraints=DEFAULT,
    )
    assert blocked is False
    assert args["discount_percent"] == 40  # clamped to ceiling, never blocked


def test_missing_discount_percent_defaults_to_zero_not_a_crash():
    args, msg, blocked = enforce_action_discount(
        AgentActionType.FLASH_SALE, {"product_id": "p1"},
        cost_price=10.0, price=20.0, constraints=DEFAULT,
    )
    assert blocked is False
    assert args["discount_percent"] == 0


def test_cart_dwell_nudge_is_ceiling_only_no_below_cost_check():
    args, msg, blocked = enforce_action_discount(
        AgentActionType.CART_DWELL_NUDGE, {"discount_percent": 90},
        cost_price=0.0, price=0.0, constraints=DEFAULT,
    )
    assert blocked is False
    assert args["discount_percent"] == 40  # clamped to ceiling, never blocked


def test_min_price_above_actual_price_clamps_to_zero_not_negative():
    # Merchant misconfigured min_price ($25) above the product's actual price
    # ($20) — floor_discount = (1 - 25/20) * 100 = -25%, which is nonsensical.
    # Must clamp to 0% (no discount), never store a negative discount.
    constraints = BusinessConstraints(
        min_profit_margin_percent=20, max_discount_percent=40,
        min_price={"p1": 25.0},
    )
    args, msg, blocked = enforce_action_discount(
        AgentActionType.FLASH_SALE, {"product_id": "p1", "discount_percent": 10},
        cost_price=10.0, price=20.0, constraints=constraints, product_id="p1",
    )
    assert blocked is False
    assert args["discount_percent"] == 0.0
    assert "0%" in msg

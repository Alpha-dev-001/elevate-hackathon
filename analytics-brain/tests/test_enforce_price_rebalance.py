from app.services.interceptor import enforce_price_rebalance
from app.models.schemas import BusinessConstraints

DEFAULT = BusinessConstraints(
    min_profit_margin_percent=20, max_discount_percent=40,
    max_uplift_percent=10, min_price={},
)


def test_downward_move_within_floor_passes_clean():
    price, msg, blocked_flag = enforce_price_rebalance(
        18.0, baseline_price=20.0, cost_price=10.0, constraints=DEFAULT,
    )
    assert price == 18.0
    assert msg == ""
    assert blocked_flag is False


def test_downward_move_below_margin_floor_clamps():
    # 20% margin floor on cost=10 is 12.0; proposing 11.0 must clamp to 12.0.
    price, msg, blocked_flag = enforce_price_rebalance(
        11.0, baseline_price=20.0, cost_price=10.0, constraints=DEFAULT,
    )
    assert price == 12.0
    assert blocked_flag is False
    assert "12" in msg


def test_downward_move_below_cost_blocks():
    price, msg, blocked_flag = enforce_price_rebalance(
        5.0, baseline_price=20.0, cost_price=10.0, constraints=DEFAULT,
    )
    assert blocked_flag is True
    assert "below" in msg.lower() or "cost" in msg.lower()


def test_upward_move_within_ceiling_passes_clean():
    price, msg, blocked_flag = enforce_price_rebalance(
        21.0, baseline_price=20.0, cost_price=10.0, constraints=DEFAULT,
    )
    assert price == 21.0
    assert msg == ""
    assert blocked_flag is False


def test_upward_move_beyond_ceiling_clamps_never_blocks():
    price, msg, blocked_flag = enforce_price_rebalance(
        30.0, baseline_price=20.0, cost_price=10.0, constraints=DEFAULT,
    )
    assert price == 22.0  # 20 * 1.10
    assert blocked_flag is False
    assert "10" in msg


def test_move_exactly_at_baseline_treated_as_upward_path():
    # new_price == baseline_price is not "downward" (not < baseline), so it
    # must go through enforce_uplift, not enforce_price — confirm it doesn't
    # spuriously apply a margin-floor clamp when baseline already clears cost.
    price, msg, blocked_flag = enforce_price_rebalance(
        20.0, baseline_price=20.0, cost_price=10.0, constraints=DEFAULT,
    )
    assert price == 20.0
    assert blocked_flag is False

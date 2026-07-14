from app.services.interceptor import enforce_price_rebalance
from app.services.tools import narrative_from_tool
from app.services.decision_engine import grounded_gmv
from app.models.schemas import BusinessConstraints


def test_clamped_price_rebalance_flows_into_narrative_title():
    """Same property test_decision_engine_interceptor.py proves for
    FLASH_SALE: the interceptor must run BEFORE narrative_from_tool, so the
    option card's title shows the real, clamped price — never Qwen's raw ask."""
    constraints = BusinessConstraints(max_uplift_percent=5, min_profit_margin_percent=15)
    raw_tool_args = {"product_id": "p1", "new_price": 30.0, "reasoning_signals": "purchases up"}

    clamped_price, constraint_check, is_blocked = enforce_price_rebalance(
        raw_tool_args["new_price"], baseline_price=20.0, cost_price=10.0, constraints=constraints,
    )
    assert is_blocked is False
    assert clamped_price == 21.0  # 20 * 1.05, not Qwen's raw 30.0

    clamped_args = dict(raw_tool_args)
    clamped_args["new_price"] = clamped_price
    narrative = narrative_from_tool(
        "propose_price_rebalance", clamped_args, "Widget", "Price review: Widget",
    )
    assert "21.00" in narrative["title"]
    assert "30.00" not in narrative["title"]


def test_grounded_gmv_returns_zero_for_price_rebalance():
    # No invented revenue number for a repricing — matches duplicate_merge's
    # existing "no grounded basis" treatment, falls back to Qwen's own
    # estimated_gmv (if any) at the run_decision_cycle call site instead.
    assert grounded_gmv("price_rebalance", anomaly_count=5, avg_price=20.0) == 0.0

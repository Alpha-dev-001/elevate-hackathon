from app.services.interceptor import enforce_action_discount
from app.services.tools import narrative_from_tool
from app.models.schemas import AgentActionType, BusinessConstraints


def test_clamped_discount_flows_into_narrative_title():
    """Proves the wiring order in run_decision_cycle: the interceptor must
    run BEFORE narrative_from_tool, so the option card's title shows the
    real, clamped number — never Qwen's raw, unsafe ask."""
    constraints = BusinessConstraints(max_discount_percent=20, min_profit_margin_percent=15)
    raw_tool_args = {"product_id": "p1", "discount_percent": 60}

    clamped_args, constraint_check, is_blocked = enforce_action_discount(
        AgentActionType.FLASH_SALE, raw_tool_args,
        cost_price=10.0, price=15.0, constraints=constraints,
    )
    assert is_blocked is False
    assert clamped_args["discount_percent"] == 20

    narrative = narrative_from_tool(
        "propose_flash_sale", clamped_args, "Widget", "velocity spike", "warm",
    )
    assert "20%" in narrative["title"]
    assert "60%" not in narrative["title"]

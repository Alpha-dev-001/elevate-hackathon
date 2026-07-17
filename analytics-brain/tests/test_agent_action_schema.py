from app.models.schemas import AgentAction, AgentActionStatus, AgentActionType


def test_agent_action_constraint_check_defaults_empty():
    action = AgentAction(
        id="a1", merchant_id="m1", promo_id="p1",
        action_type=AgentActionType.FLASH_SALE, trigger="t", title="t",
        description="d", estimated_gmv=0, estimated_confidence=0.5,
        payload={}, brand_check="", created_at=0,
    )
    assert action.constraint_check == ""


def test_blocked_at_execution_status_exists():
    assert AgentActionStatus.BLOCKED_AT_EXECUTION == "blocked_at_execution"


def test_agent_action_role_field_defaults_to_none():
    from app.models.schemas import AgentAction, AgentActionType, AgentActionStatus

    action = AgentAction(
        id="a1", merchant_id="m1", promo_id="p1",
        action_type=AgentActionType.FLASH_SALE, trigger="t", title="t",
        description="d", estimated_gmv=0, estimated_confidence=0.5,
        payload={}, brand_check="", status=AgentActionStatus.PENDING,
        created_at=0,
    )
    assert action.role is None


def test_agent_action_role_field_accepts_a_role_name():
    from app.models.schemas import AgentAction, AgentActionType, AgentActionStatus

    action = AgentAction(
        id="a1", merchant_id="m1", promo_id="p1",
        action_type=AgentActionType.FLASH_SALE, trigger="t", title="t",
        description="d", estimated_gmv=0, estimated_confidence=0.5,
        payload={}, brand_check="", status=AgentActionStatus.PENDING,
        created_at=0, role="pricing_strategist",
    )
    assert action.role == "pricing_strategist"

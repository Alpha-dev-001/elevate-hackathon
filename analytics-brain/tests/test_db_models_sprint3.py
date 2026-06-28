from app.models.db_models import MerchantDB, AgentActionDB


def test_merchant_has_qwen_memory_column():
    assert "qwen_memory" in MerchantDB.__table__.columns


def test_agent_action_has_outcome_columns():
    cols = AgentActionDB.__table__.columns
    assert "merchant_behavior" in cols
    assert "trigger_description" in cols

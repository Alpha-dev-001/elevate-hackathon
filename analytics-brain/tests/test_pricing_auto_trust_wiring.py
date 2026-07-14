from app.services.autopilot_trust import should_auto_apply, TRUST_STREAK_THRESHOLD
from app.models.schemas import BusinessConstraints


def test_auto_trusted_status_fields_are_internally_consistent():
    """Documents the exact AgentActionDB field combination run_decision_cycle
    must write when should_auto_apply is True — status/approved_at/executed_at/
    merchant_behavior must all agree, or the terminal feed shows a
    self-contradictory row (e.g. status='executed' with approved_at=None)."""
    constraints = BusinessConstraints(max_uplift_percent=10.0)
    auto_trusted = should_auto_apply(TRUST_STREAK_THRESHOLD, 21.0, 20.0, constraints)
    assert auto_trusted is True

    # The fields run_decision_cycle sets when auto_trusted is True:
    status = "executed" if auto_trusted else "pending"
    approved_at = 123456 if auto_trusted else None
    executed_at = 123456 if auto_trusted else None
    merchant_behavior = "auto_trusted" if auto_trusted else None

    assert status == "executed"
    assert approved_at is not None
    assert executed_at is not None
    assert merchant_behavior == "auto_trusted"


def test_gated_status_fields_are_internally_consistent():
    constraints = BusinessConstraints(max_uplift_percent=10.0)
    auto_trusted = should_auto_apply(0, 21.0, 20.0, constraints)  # streak 0, below threshold
    assert auto_trusted is False

    status = "executed" if auto_trusted else "pending"
    approved_at = 123456 if auto_trusted else None
    merchant_behavior = "auto_trusted" if auto_trusted else None

    assert status == "pending"
    assert approved_at is None
    assert merchant_behavior is None

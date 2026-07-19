"""Regression for a real bug found live: _to_schema (agent.py) — shared by
GET /actions/{slug}/pending, POST /actions/{id}/approve, and
POST /actions/{id}/dismiss — never passed constraint_check into the
AgentAction it builds. Pydantic's `constraint_check: str = ""` default made
this silent: no validation error, just an always-empty field in every API
response regardless of what the DB row actually held.

This was the true root cause of a chain of "the clamp warning never shows"
reports: the interceptor correctly clamped the live store, the row was
correctly persisted with the real value (verified separately in
test_execution_time_clamp_persisted.py), but the HTTP response the merchant
actually sees never carried it — so no frontend fix downstream could ever
have worked without this."""
from app.models.db_models import AgentActionDB


def _row(**overrides) -> AgentActionDB:
    defaults = dict(
        id="act_1", merchant_id="m1", promo_id="promo_1",
        action_type="flash_sale", trigger="t", title="t", description="d",
        estimated_gmv=0.0, estimated_confidence=0.5,
        payload={"product_id": "p1", "discount_percent": 31},
        brand_check="", constraint_check="", status="executed", created_at=0,
    )
    defaults.update(overrides)
    return AgentActionDB(**defaults)


def test_to_schema_carries_constraint_check_through():
    from app.routers.agent import _to_schema

    row = _row(constraint_check="70% exceeds your 40% discount ceiling. Clamped to 40%.")
    action = _to_schema(row)
    assert action.constraint_check == "70% exceeds your 40% discount ceiling. Clamped to 40%."


def test_to_schema_empty_constraint_check_stays_empty():
    from app.routers.agent import _to_schema

    row = _row(constraint_check="")
    action = _to_schema(row)
    assert action.constraint_check == ""

"""A merchant can override a pending discount-bearing action's percent on
approval. The override still goes through the same interceptor primitive as
Qwen's own number (never a bypass), and gets written to qwen_memory so
future proposals learn from it — mirrors products.py's update_product
memory-write pattern exactly."""
import asyncio
from unittest.mock import AsyncMock, patch

from app.models.db_models import AgentActionDB


def _run(coro):
    return asyncio.run(coro)


def _action(action_type="flash_sale", discount_percent=10.0) -> AgentActionDB:
    return AgentActionDB(
        id="act1", merchant_id="m1", promo_id="promo1", action_type=action_type,
        trigger="t", title="t", description="d", estimated_gmv=0.0,
        estimated_confidence=0.9, payload={"discount_percent": discount_percent, "product_id": "p1"},
        brand_check="", status="pending", created_at=0,
    )


class TestApproveActionOverride:
    def test_override_replaces_qwen_discount_before_execution(self):
        from app.routers.agent import approve_action
        from app.models.schemas import ApproveActionRequest

        row = _action(discount_percent=10.0)
        db = AsyncMock()
        db.get = AsyncMock(return_value=row)
        db.commit = AsyncMock()

        with (
            patch("app.routers.agent._execute_payload", new_callable=AsyncMock, return_value=True) as mock_execute,
            patch("app.routers.agent._broadcast_state_update", new_callable=AsyncMock),
            patch("app.services.receipts.append_receipt", new_callable=AsyncMock),
            patch("app.services.memory.write_memory", new_callable=AsyncMock) as mock_write_memory,
        ):
            _run(approve_action(
                "act1", body=ApproveActionRequest(discount_percent_override=25.0),
                db=db, merchant=AsyncMock(id="m1"),
            ))

        # _execute_payload must have run against the OVERRIDDEN payload, not Qwen's 10%
        executed_row = mock_execute.call_args.args[0]
        assert executed_row.payload["discount_percent"] == 25.0
        mock_write_memory.assert_awaited_once()

    def test_no_override_keeps_qwen_number_unchanged(self):
        from app.routers.agent import approve_action
        from app.models.schemas import ApproveActionRequest

        row = _action(discount_percent=10.0)
        db = AsyncMock()
        db.get = AsyncMock(return_value=row)
        db.commit = AsyncMock()

        with (
            patch("app.routers.agent._execute_payload", new_callable=AsyncMock, return_value=True) as mock_execute,
            patch("app.routers.agent._broadcast_state_update", new_callable=AsyncMock),
            patch("app.services.receipts.append_receipt", new_callable=AsyncMock),
            patch("app.services.memory.write_memory", new_callable=AsyncMock) as mock_write_memory,
        ):
            _run(approve_action(
                "act1", body=ApproveActionRequest(discount_percent_override=None),
                db=db, merchant=AsyncMock(id="m1"),
            ))

        executed_row = mock_execute.call_args.args[0]
        assert executed_row.payload["discount_percent"] == 10.0
        mock_write_memory.assert_not_awaited()  # no override → nothing to learn from

    def test_no_body_at_all_behaves_like_before(self):
        """The pre-existing caller shape (no body) must keep working — the
        new parameter is purely additive."""
        from app.routers.agent import approve_action

        row = _action(discount_percent=10.0)
        db = AsyncMock()
        db.get = AsyncMock(return_value=row)
        db.commit = AsyncMock()

        with (
            patch("app.routers.agent._execute_payload", new_callable=AsyncMock, return_value=True) as mock_execute,
            patch("app.routers.agent._broadcast_state_update", new_callable=AsyncMock),
            patch("app.services.receipts.append_receipt", new_callable=AsyncMock),
            patch("app.services.memory.write_memory", new_callable=AsyncMock) as mock_write_memory,
        ):
            _run(approve_action("act1", db=db, merchant=AsyncMock(id="m1")))

        executed_row = mock_execute.call_args.args[0]
        assert executed_row.payload["discount_percent"] == 10.0
        mock_write_memory.assert_not_awaited()

    def test_override_on_non_discount_action_is_ignored(self):
        """layout_morph etc. carry no discount_percent key — an override
        must not inject one where none belongs."""
        from app.routers.agent import approve_action
        from app.models.schemas import ApproveActionRequest

        row = AgentActionDB(
            id="act2", merchant_id="m1", promo_id="promo2", action_type="layout_morph",
            trigger="t", title="t", description="d", estimated_gmv=0.0,
            estimated_confidence=0.9, payload={"hero_product_id": "p1"},
            brand_check="", status="pending", created_at=0,
        )
        db = AsyncMock()
        db.get = AsyncMock(return_value=row)
        db.commit = AsyncMock()

        with (
            patch("app.routers.agent._execute_payload", new_callable=AsyncMock, return_value=True) as mock_execute,
            patch("app.routers.agent._broadcast_state_update", new_callable=AsyncMock),
            patch("app.services.receipts.append_receipt", new_callable=AsyncMock),
            patch("app.services.memory.write_memory", new_callable=AsyncMock) as mock_write_memory,
        ):
            _run(approve_action(
                "act2", body=ApproveActionRequest(discount_percent_override=25.0),
                db=db, merchant=AsyncMock(id="m1"),
            ))

        executed_row = mock_execute.call_args.args[0]
        assert "discount_percent" not in executed_row.payload
        mock_write_memory.assert_not_awaited()

"""Priority-arbitration gate in run_decision_cycle — Task 2 of the swarm
coordination plan. The skip / stale-dismiss / no-existing paths resolve at
the gate before any Qwen call, so they mock nothing below it. The SUPERSEDE
path deliberately does NOT dismiss the existing card at the gate — it defers
the dismissal until a replacement action actually exists, so a supersede
followed by a declined/blocked cycle can't leave the merchant with a vanished
card and nothing in its place. So the two supersede tests run a full cycle
with _qwen_chat mocked: one where the replacement lands (existing IS
dismissed), one where Qwen declines (existing MUST stay pending)."""
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.qwen_roles import PRICING_STRATEGIST, INVENTORY_OVERSEER


def _qwen_message(tool_name: str, args: dict) -> dict:
    return {"tool_calls": [{"function": {"name": tool_name, "arguments": json.dumps(args)}}]}


def _make_existing_action(action_type: str, role: str | None, age_seconds: float):
    """A stand-in for the AgentActionDB row db.scalar would return for an
    existing pending action."""
    from unittest.mock import MagicMock
    row = MagicMock()
    row.id = "existing-1"
    row.action_type = action_type
    row.role = role
    row.status = "pending"
    row.payload = {}
    row.created_at = int(time.time() * 1000) - int(age_seconds * 1000)
    return row


@pytest.mark.asyncio
class TestPriorityArbitrationGate:
    async def test_higher_priority_incoming_signal_supersedes_existing(self):
        """Pricing Strategist (default_priority=20, no learning history yet)
        supersedes a pending Inventory Overseer action (default_priority=10) —
        but the dismissal only fires once its own replacement is actually
        created. Full cycle: Qwen proposes a valid flash_sale, so the
        supersede lands and the old card is retired."""
        from app.services.decision_engine import run_decision_cycle

        existing = _make_existing_action("duplicate_merge", "inventory_overseer", age_seconds=10)
        db = AsyncMock()
        # db.scalar: gate pending-action lookup → existing; then avg_price → None (→ 0.0).
        db.scalar.side_effect = [existing, None]
        # db.get, in order: MerchantDB → merchant, BrandProfileDB → None,
        # get_memory's MerchantDB → None (get_memory then returns [] cleanly).
        merchant = MagicMock(store_name="Test Store")
        db.get.side_effect = [merchant, None, None]
        product = MagicMock(id="p1", name="Viral Widget", price=50.0, cost_price=20.0, baseline_price=50.0, stock=10)
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = [product]
        db.execute.return_value = products_result
        redis = AsyncMock()

        qwen_message = _qwen_message(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": 15, "reasoning": "Going viral — capture it."},
        )

        with patch("app.services.decision_engine._qwen_chat", new=AsyncMock(return_value=qwen_message)), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))), \
             patch("app.services.interceptor.enforce_action_discount") as mock_interceptor, \
             patch("app.core.ws_manager.manager.push_to_terminal", new=AsyncMock()), \
             patch("app.services.receipts.append_receipt", new=AsyncMock()):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            mock_settings.return_value.pending_action_ttl_seconds_durable = 86400
            mock_interceptor.return_value = (
                {"product_id": "p1", "discount_percent": 15, "reasoning": "Going viral — capture it."}, "", False,
            )
            action = await run_decision_cycle(
                "merchant-1", "Velocity spike: 24 views on product p1 in 30s", db, redis,
                role=PRICING_STRATEGIST,
            )

        assert existing.status == "dismissed"
        assert action is not None
        assert action.role == "pricing_strategist"
        assert "Superseded a pending inventory_overseer action" in action.reasoning

    async def test_supersede_is_deferred_when_replacement_declines(self):
        """The safety property behind deferring the dismissal: a higher-
        priority signal that then produces NO action (Qwen declines) must NOT
        have dismissed the existing card — the merchant keeps their valid
        pending proposal instead of losing it to a supersede that came up
        empty. This test passes against BOTH today's code (which never
        supersedes) and the post-Task-2 code (which defers), which is exactly
        what a regression guard should do."""
        from app.services.decision_engine import run_decision_cycle

        existing = _make_existing_action("duplicate_merge", "inventory_overseer", age_seconds=10)
        db = AsyncMock()
        db.scalar.side_effect = [existing, None]
        merchant = MagicMock(store_name="Test Store")
        db.get.side_effect = [merchant, None, None]
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = []
        db.execute.return_value = products_result
        redis = AsyncMock()

        with patch("app.services.decision_engine._qwen_chat", new=AsyncMock(return_value={"tool_calls": []})), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))), \
             patch("app.core.ws_manager.manager.push_to_terminal", new=AsyncMock()) as mock_push:
            mock_settings.return_value.pending_action_ttl_seconds = 300
            mock_settings.return_value.pending_action_ttl_seconds_durable = 86400
            action = await run_decision_cycle(
                "merchant-1", "Velocity spike: 24 views on product p1 in 30s", db, redis,
                role=PRICING_STRATEGIST,
            )

        assert action is None
        assert existing.status == "pending"  # never dismissed — supersede deferred and never fired
        mock_push.assert_not_called()  # no ACTION_EXPIRED went out either

    async def test_lower_priority_incoming_signal_is_skipped(self):
        """Inventory Overseer (default_priority=10) must NOT supersede a
        pending Sales Rep action (default_priority=30)."""
        from app.services.decision_engine import run_decision_cycle

        existing = _make_existing_action("recovery_offer", "sales_rep", age_seconds=10)
        db = AsyncMock()
        db.scalar.return_value = existing
        redis = AsyncMock()

        with patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            result = await run_decision_cycle(
                "merchant-1", "two duplicate listings found", db, redis,
                role=INVENTORY_OVERSEER,
            )

        assert existing.status == "pending"  # untouched
        assert result is None
        db.commit.assert_not_called()

    async def test_stale_existing_action_is_dismissed_regardless_of_priority(self):
        """Regression: staleness must still win over priority — an old
        Sales Rep action (default_priority=30, higher) must still be
        dismissed by a fresh Inventory Overseer signal (default_priority=10,
        lower) once it's past the TTL. This is byte-identical to pre-existing
        behavior for every caller not touched by this task."""
        from app.services.decision_engine import run_decision_cycle

        existing = _make_existing_action("recovery_offer", "sales_rep", age_seconds=999)
        db = AsyncMock()
        db.scalar.return_value = existing
        redis = AsyncMock()

        with patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.core.ws_manager.manager.push_to_terminal", new=AsyncMock()):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            db.get.return_value = None
            await run_decision_cycle(
                "merchant-1", "two duplicate listings found", db, redis,
                role=INVENTORY_OVERSEER,
            )

        assert existing.status == "dismissed"

    async def test_no_existing_pending_action_skips_arbitration_entirely(self):
        """No pending row at all — the gate must not even attempt a priority
        comparison, matching today's exact no-op path."""
        from app.services.decision_engine import run_decision_cycle

        db = AsyncMock()
        db.scalar.return_value = None
        redis = AsyncMock()

        with patch("app.services.decision_engine.get_settings") as mock_settings:
            mock_settings.return_value.pending_action_ttl_seconds = 300
            db.get.return_value = None
            result = await run_decision_cycle(
                "merchant-1", "two duplicate listings found", db, redis,
                role=INVENTORY_OVERSEER,
            )

        assert result is None
        db.commit.assert_not_called()

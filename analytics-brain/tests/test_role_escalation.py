"""Single-hop role escalation — Task 4 of the swarm coordination plan.
_qwen_chat is mocked at both call sites (outer role's call, inner target
role's call) so these tests exercise the ESCALATION WIRING (tool detection,
permission check, recursive call shape, reasoning merge, hard single-hop
cap) without a real API call — see test_role_escalation_live.py (Task 5)
for the real end-to-end proof."""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.qwen_roles import STORE_CURATOR, PRICING_STRATEGIST


def _qwen_message(tool_name: str, args: dict):
    import json
    return {
        "tool_calls": [{"function": {"name": tool_name, "arguments": json.dumps(args)}}],
    }


@pytest.mark.asyncio
class TestRoleEscalation:
    async def test_escalation_tool_call_triggers_a_second_call_scoped_to_target_role(self):
        from app.services.decision_engine import run_decision_cycle

        outer_message = _qwen_message(
            "propose_escalate_to_role",
            {"target_role": "pricing_strategist", "reasoning": "This needs a price cut, not new copy."},
        )
        inner_message = _qwen_message(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": 15, "reasoning": "Overpriced vs category peers."},
        )

        db = AsyncMock()
        db.scalar.return_value = None  # no pending action, both calls pass the gate
        merchant = MagicMock(store_name="Test Store")
        db.get.return_value = merchant
        product = MagicMock(id="p1", name="Test Product", price=50.0, cost_price=20.0, baseline_price=50.0, stock=10)
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = [product]
        db.execute.return_value = products_result
        redis = AsyncMock()

        call_count = 0

        async def fake_qwen_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            return outer_message if call_count == 1 else inner_message

        with patch("app.services.decision_engine._qwen_chat", new=fake_qwen_chat), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))), \
             patch("app.services.interceptor.enforce_action_discount") as mock_interceptor, \
             patch("app.core.ws_manager.manager.push_to_terminal", new=AsyncMock()), \
             patch("app.services.receipts.append_receipt", new=AsyncMock()):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            mock_interceptor.return_value = ({"product_id": "p1", "discount_percent": 15, "reasoning": "Overpriced vs category peers."}, "", False)
            action = await run_decision_cycle(
                "merchant-1", "Store review: 40 views, 0 orders in the last 24h for \"Test Product\"",
                db, redis, role=STORE_CURATOR,
            )

        assert call_count == 2
        assert action is not None
        assert action.role == "pricing_strategist"
        assert "Overpriced vs category peers" in action.reasoning

    async def test_second_call_declining_resolves_to_none(self):
        from app.services.decision_engine import run_decision_cycle

        outer_message = _qwen_message(
            "propose_escalate_to_role",
            {"target_role": "pricing_strategist", "reasoning": "Needs a price look."},
        )
        db = AsyncMock()
        db.scalar.return_value = None
        merchant = MagicMock(store_name="Test Store")
        db.get.return_value = merchant
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = []
        db.execute.return_value = products_result
        redis = AsyncMock()

        call_count = 0

        async def fake_qwen_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            return outer_message if call_count == 1 else {"tool_calls": []}

        with patch("app.services.decision_engine._qwen_chat", new=fake_qwen_chat), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            action = await run_decision_cycle(
                "merchant-1", "Store review: 40 views, 0 orders", db, redis, role=STORE_CURATOR,
            )

        assert call_count == 2
        assert action is None

    async def test_second_call_erroring_resolves_to_none(self):
        from app.services.decision_engine import run_decision_cycle
        from app.services.brand import BrandGenerationError

        outer_message = _qwen_message(
            "propose_escalate_to_role",
            {"target_role": "pricing_strategist", "reasoning": "Needs a price look."},
        )
        db = AsyncMock()
        db.scalar.return_value = None
        merchant = MagicMock(store_name="Test Store")
        db.get.return_value = merchant
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = []
        db.execute.return_value = products_result
        redis = AsyncMock()

        call_count = 0

        async def fake_qwen_chat(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return outer_message
            raise BrandGenerationError("qwen-max call failed after 3 attempts")

        with patch("app.services.decision_engine._qwen_chat", new=fake_qwen_chat), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            action = await run_decision_cycle(
                "merchant-1", "Store review: 40 views, 0 orders", db, redis, role=STORE_CURATOR,
            )

        assert action is None

    async def test_escalation_to_a_role_not_permitted_is_treated_as_declined(self):
        """Sales Rep has no can_escalate_to at all — if Qwen somehow still
        emitted this tool name (should be unreachable given tool-visibility
        gating, but defensive), it must not silently execute a hand-off."""
        from app.services.decision_engine import run_decision_cycle
        from app.services.qwen_roles import SALES_REP

        message = _qwen_message(
            "propose_escalate_to_role",
            {"target_role": "pricing_strategist", "reasoning": "irrelevant"},
        )
        db = AsyncMock()
        db.scalar.return_value = None
        redis = AsyncMock()

        with patch("app.services.decision_engine._qwen_chat", new=AsyncMock(return_value=message)), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            db.get.return_value = MagicMock(store_name="Test Store")
            products_result = MagicMock()
            products_result.scalars.return_value.all.return_value = []
            db.execute.return_value = products_result
            action = await run_decision_cycle(
                "merchant-1", "Cart abandon surge", db, redis, role=SALES_REP,
            )

        assert action is None

    async def test_inner_call_never_receives_the_escalate_tool_even_if_target_role_had_one(self):
        """Hard single-hop cap: regardless of what can_escalate_to is
        configured as for the TARGET role, the recursive inner call must
        never be offered the escalation tool. Verified by patching
        PRICING_STRATEGIST's can_escalate_to (via a throwaway QwenRole with
        the same tool_names) to a non-empty tuple and confirming the tools
        list passed to _qwen_chat's second call excludes it anyway."""
        from dataclasses import replace
        from app.services.decision_engine import run_decision_cycle
        from app.services.qwen_roles import ESCALATE_TOOL_NAME

        hypothetically_escalating_pricing = replace(
            PRICING_STRATEGIST, can_escalate_to=(STORE_CURATOR,)
        )

        outer_message = _qwen_message(
            "propose_escalate_to_role",
            {"target_role": "pricing_strategist", "reasoning": "Needs a price look."},
        )
        db = AsyncMock()
        db.scalar.return_value = None
        db.get.return_value = MagicMock(store_name="Test Store")
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = []
        db.execute.return_value = products_result
        redis = AsyncMock()

        seen_tools_by_call: list[list[dict]] = []

        async def fake_qwen_chat(**kwargs):
            seen_tools_by_call.append(kwargs.get("tools", []))
            if len(seen_tools_by_call) == 1:
                return outer_message
            return {"tool_calls": []}

        with patch("app.services.decision_engine._qwen_chat", new=fake_qwen_chat), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))), \
             patch("app.services.qwen_roles.ALL_ROLES", (hypothetically_escalating_pricing, STORE_CURATOR)):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            await run_decision_cycle(
                "merchant-1", "Store review: 40 views, 0 orders", db, redis, role=STORE_CURATOR,
            )

        assert len(seen_tools_by_call) == 2
        second_call_tool_names = {t["function"]["name"] for t in seen_tools_by_call[1]}
        assert ESCALATE_TOOL_NAME not in second_call_tool_names

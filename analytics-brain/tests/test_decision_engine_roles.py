"""role wiring in compose_decision_prompt / run_decision_cycle — Task 2 of
the Qwen swarm roles plan. compose_decision_prompt's role behavior is pure
and unit-tested directly; run_decision_cycle's tool-scoping-from-role
behavior needs the real _qwen_chat call mocked, same pattern
test_decision_engine_pricing.py already uses for prompt_override."""
from app.services.decision_engine import compose_decision_prompt
from app.services.qwen_roles import PRICING_STRATEGIST, INVENTORY_OVERSEER


class TestComposeDecisionPromptRole:
    def test_no_role_keeps_the_generic_intro(self):
        prompt = compose_decision_prompt(
            store_name="Haree", mood="refined", brand_voice="quiet",
            brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
            anomaly_description="34 views in 28s",
        )
        assert prompt.startswith('You are the autonomous commerce brain for "Haree".')

    def test_role_swaps_in_its_mission_line(self):
        prompt = compose_decision_prompt(
            store_name="Haree", mood="refined", brand_voice="quiet",
            brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
            anomaly_description="34 views in 28s",
            role=PRICING_STRATEGIST,
        )
        assert prompt.startswith('You are the Pricing Strategist for "Haree"')
        assert "autonomous commerce brain" not in prompt

    def test_different_role_different_intro(self):
        prompt = compose_decision_prompt(
            store_name="Haree", mood="refined", brand_voice="quiet",
            brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
            anomaly_description="two duplicate listings found",
            role=INVENTORY_OVERSEER,
        )
        assert prompt.startswith('You are the Inventory Overseer for "Haree"')

    def test_role_does_not_break_memory_block(self):
        prompt = compose_decision_prompt(
            store_name="Haree", mood="refined", brand_voice="quiet",
            brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
            anomaly_description="34 views in 28s",
            memory_context="prior outcome: approved",
            role=PRICING_STRATEGIST,
        )
        assert "prior outcome: approved" in prompt

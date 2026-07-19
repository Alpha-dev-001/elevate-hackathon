"""Regression coverage for a real bug found live: run_store_review's
underperformer path discarded the real, DB-verified product_id it had
already found (`_, description = found`) and passed only a free-text
description to run_decision_cycle with no target_product_id. Qwen, reading
a full multi-product catalog plus that description, invented a
plausible-looking but nonexistent product_id ("prod_123456789abc") in its
own tool call — which then got persisted verbatim as the action's payload,
producing a pending card that could never be approved (the interceptor's
execution-time product lookup always misses and blocks it).

Two things needed fixing:
1. store_review.py must not discard the real id.
2. decision_engine.run_decision_cycle must actually use a caller-supplied
   target_product_id to correct the FINAL PERSISTED payload, not just the
   interceptor's cost/price lookup and the narrative's product name — it
   was already "authoritative" for those two, but not for the thing that
   actually gets executed later.
"""
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.qwen_roles import STORE_CURATOR, PRICING_STRATEGIST


def _qwen_message(tool_name: str, args: dict):
    import json
    return {"tool_calls": [{"function": {"name": tool_name, "arguments": json.dumps(args)}}]}


@pytest.mark.asyncio
class TestTargetProductIdOverridesHallucination:
    async def test_hallucinated_product_id_in_tool_args_is_overridden_by_target_product_id(self):
        """Qwen's tool call names a product_id that doesn't match the real,
        caller-verified target — the persisted payload must use the real one."""
        from app.services.decision_engine import run_decision_cycle

        message = _qwen_message(
            "propose_price_rebalance",
            {"product_id": "prod_123456789abc", "new_price": 52.5,
             "reasoning": "No views, cart-adds, or purchases in 7 days."},
        )

        db = AsyncMock()
        db.scalar.return_value = None  # no existing pending action
        # A plain MagicMock, not AsyncMock's own auto-mocked default — its
        # attributes must behave synchronously (generated_brand.get(...) etc.),
        # matching test_role_escalation.py's established pattern.
        db.get.return_value = MagicMock(store_name="Test Store", generated_brand=None)
        real_product = MagicMock(
            id="prod_real_casablanca", name="Casablanca Embroidered Strap Slides",
            price=75.0, cost_price=45.0, baseline_price=75.0, stock=10,
        )
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = [real_product]
        db.execute.return_value = products_result
        redis = AsyncMock()

        with patch("app.services.decision_engine._qwen_chat", new=AsyncMock(return_value=message)), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints",
                   new=AsyncMock(return_value=MagicMock(
                       min_profit_margin_percent=15.0, max_uplift_percent=0.0, max_discount_percent=40.0,
                   ))), \
             patch("app.services.interceptor.enforce_price_rebalance") as mock_interceptor, \
             patch("app.core.ws_manager.manager.push_to_terminal", new=AsyncMock()), \
             patch("app.services.receipts.append_receipt", new=AsyncMock()):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            mock_settings.return_value.pending_action_ttl_seconds_durable = 86400
            mock_interceptor.return_value = (52.5, "", False)
            action = await run_decision_cycle(
                "merchant-1",
                'Store review: "Casablanca Embroidered Strap Slides" — no views, cart-adds, '
                "or purchases in the last 7 days.",
                db, redis, role=STORE_CURATOR, target_product_id="prod_real_casablanca",
            )

        assert action is not None
        # The real, verified product must win — never Qwen's invented id.
        assert action.payload["product_id"] == "prod_real_casablanca"
        assert action.payload["product_id"] != "prod_123456789abc"

    async def test_no_target_product_id_leaves_tool_args_product_id_untouched(self):
        """Every pre-existing caller that never passes target_product_id must
        see byte-identical behavior — this is an additive correction, not a
        general product_id rewrite."""
        from app.services.decision_engine import run_decision_cycle

        message = _qwen_message(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": 15, "reasoning": "Velocity spike."},
        )

        db = AsyncMock()
        db.scalar.return_value = None
        db.get.return_value = MagicMock(store_name="Test Store", generated_brand=None)
        product = MagicMock(id="p1", name="Test Product", price=50.0, cost_price=20.0, baseline_price=50.0, stock=10)
        products_result = MagicMock()
        products_result.scalars.return_value.all.return_value = [product]
        db.execute.return_value = products_result
        redis = AsyncMock()

        with patch("app.services.decision_engine._qwen_chat", new=AsyncMock(return_value=message)), \
             patch("app.services.decision_engine.get_settings") as mock_settings, \
             patch("app.services.learning.load_role_learning", new=AsyncMock(return_value=None)), \
             patch("app.services.profile.load_constraints", new=AsyncMock(return_value=MagicMock(max_discount_percent=40.0))), \
             patch("app.services.interceptor.enforce_action_discount") as mock_interceptor, \
             patch("app.core.ws_manager.manager.push_to_terminal", new=AsyncMock()), \
             patch("app.services.receipts.append_receipt", new=AsyncMock()):
            mock_settings.return_value.pending_action_ttl_seconds = 300
            mock_interceptor.return_value = ({"product_id": "p1", "discount_percent": 15, "reasoning": "Velocity spike."}, "", False)
            action = await run_decision_cycle(
                "merchant-1", "Velocity spike on p1", db, redis, role=PRICING_STRATEGIST,
            )

        assert action is not None
        assert action.payload["product_id"] == "p1"


class TestRunStoreReviewPassesRealProductId:
    def test_underperformer_path_no_longer_discards_the_verified_product_id(self):
        import asyncio
        from app.services import store_review

        async def _scenario():
            with patch(
                "app.services.store_review.find_underperformer",
                new=AsyncMock(return_value=("prod_real", "42 views, 0 orders in the last 24h")),
            ), patch(
                "app.services.duplicate_scan.run_duplicate_scan", new=AsyncMock(return_value=None),
            ), patch(
                "app.services.store_review.check_scarcity_signals", new=AsyncMock(return_value=None),
            ), patch(
                "app.services.decision_engine.run_decision_cycle", new=AsyncMock(return_value=MagicMock()),
            ) as mock_cycle:
                await store_review.run_store_review("merchant-1", db=AsyncMock(), redis=AsyncMock())

            assert mock_cycle.await_args.kwargs.get("target_product_id") == "prod_real"

        asyncio.run(_scenario())

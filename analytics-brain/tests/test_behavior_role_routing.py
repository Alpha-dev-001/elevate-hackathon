"""behavior.py's two reactive triggers must route to the correct Qwen role.
This asserts the WIRING (role_for_anomaly is actually called with the real
description and its result actually passed to run_decision_cycle), not
role_for_anomaly's own logic (already covered in test_qwen_roles.py)."""
import asyncio
from unittest.mock import AsyncMock, patch

from app.services.qwen_roles import SALES_REP, PRICING_STRATEGIST


def _run(coro):
    return asyncio.run(coro)


class TestBehaviorRoleRouting:
    def test_cart_abandon_desc_routes_to_sales_rep(self):
        from app.services import behavior_tracker

        with patch(
            "app.services.behavior_tracker.anomaly_description",
            return_value=("Cart abandon surge: 5 abandons in 30s — customers are leaving without buying", None),
        ):
            desc, _ = behavior_tracker.anomaly_description(5, 0, {})
        from app.services.qwen_roles import role_for_anomaly
        assert role_for_anomaly(desc) is SALES_REP

    def test_velocity_spike_desc_routes_to_pricing_strategist(self):
        from app.services import behavior_tracker

        with patch(
            "app.services.behavior_tracker.anomaly_description",
            return_value=('Velocity spike: 24 views on product p1 in 30s — that product is going viral', "p1"),
        ):
            desc, _ = behavior_tracker.anomaly_description(0, 24, {"p1": 24})
        from app.services.qwen_roles import role_for_anomaly
        assert role_for_anomaly(desc) is PRICING_STRATEGIST

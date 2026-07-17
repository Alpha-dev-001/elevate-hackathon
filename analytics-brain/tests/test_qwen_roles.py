import pytest

from app.services.qwen_roles import (
    ALL_ROLES,
    PRICING_STRATEGIST,
    SALES_REP,
    INVENTORY_OVERSEER,
    STORE_CURATOR,
    get_role_tools,
    role_for_action_type,
    role_for_anomaly,
    role_by_name,
)
from app.services.tools import DECISION_TOOLS


def test_every_tool_belongs_to_exactly_one_role():
    all_tool_names = {t["function"]["name"] for t in DECISION_TOOLS}
    assigned = []
    for role in ALL_ROLES:
        assigned.extend(role.tool_names)
    assert sorted(assigned) == sorted(all_tool_names), (
        "every DECISION_TOOLS entry must belong to exactly one role, no gaps, no overlaps"
    )
    assert len(assigned) == len(set(assigned)), "a tool_name appears in more than one role"


def test_get_role_tools_returns_only_that_roles_tools():
    tools = get_role_tools(PRICING_STRATEGIST)
    names = {t["function"]["name"] for t in tools}
    assert names == {"propose_flash_sale", "propose_scarcity_price", "propose_price_rebalance"}


def test_get_role_tools_preserves_decision_tools_shape():
    tools = get_role_tools(INVENTORY_OVERSEER)
    assert tools[0]["type"] == "function"
    assert "parameters" in tools[0]["function"]
    assert tools[0]["function"]["name"] == "propose_duplicate_merge"


def test_sales_rep_tools():
    names = {t["function"]["name"] for t in get_role_tools(SALES_REP)}
    assert names == {"propose_recovery_offer", "propose_cart_dwell_nudge", "propose_feature_product"}


def test_store_curator_tools():
    names = {t["function"]["name"] for t in get_role_tools(STORE_CURATOR)}
    assert names == {"propose_layout_morph", "propose_copy_rewrite"}


class TestRoleForActionType:
    def test_flash_sale_is_pricing_strategist(self):
        assert role_for_action_type("flash_sale") == "pricing_strategist"

    def test_recovery_offer_is_sales_rep(self):
        assert role_for_action_type("recovery_offer") == "sales_rep"

    def test_duplicate_merge_is_inventory_overseer(self):
        assert role_for_action_type("duplicate_merge") == "inventory_overseer"

    def test_layout_morph_is_store_curator(self):
        assert role_for_action_type("layout_morph") == "store_curator"

    def test_copy_rewrite_is_store_curator(self):
        assert role_for_action_type("copy_rewrite") == "store_curator"

    def test_price_rebalance_is_pricing_strategist(self):
        assert role_for_action_type("price_rebalance") == "pricing_strategist"

    def test_cart_dwell_nudge_is_sales_rep(self):
        assert role_for_action_type("cart_dwell_nudge") == "sales_rep"

    def test_feature_product_is_sales_rep(self):
        assert role_for_action_type("feature_product") == "sales_rep"

    def test_scarcity_price_is_pricing_strategist(self):
        assert role_for_action_type("scarcity_price") == "pricing_strategist"

    def test_unknown_action_type_returns_none(self):
        assert role_for_action_type("not_a_real_action") is None


class TestRoleForAnomaly:
    def test_cart_abandon_surge_is_sales_rep(self):
        role = role_for_anomaly(
            "Cart abandon surge: 5 abandons in 30s — customers are leaving without buying"
        )
        assert role is SALES_REP

    def test_velocity_spike_is_pricing_strategist(self):
        role = role_for_anomaly(
            'Velocity spike: 24 views on product p1 in 30s — that product is going viral'
        )
        assert role is PRICING_STRATEGIST

    def test_unrecognized_prefix_raises(self):
        with pytest.raises(ValueError):
            role_for_anomaly("Some other anomaly type nobody expected")


def test_default_priority_values():
    assert SALES_REP.default_priority == 30
    assert PRICING_STRATEGIST.default_priority == 20
    assert INVENTORY_OVERSEER.default_priority == 10
    assert STORE_CURATOR.default_priority == 10


class TestRoleByName:
    def test_finds_a_real_role(self):
        assert role_by_name("sales_rep") is SALES_REP

    def test_unknown_name_returns_none(self):
        assert role_by_name("not_a_real_role") is None

    def test_none_returns_none(self):
        assert role_by_name(None) is None

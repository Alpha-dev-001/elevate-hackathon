"""Tests for app.services.tools — tool definitions, narrative generation, mapping."""
import pytest
from app.services.tools import (
    DECISION_TOOLS,
    TOOL_TO_ACTION_TYPE,
    narrative_from_tool,
    parse_tool_args,
)
from app.models.schemas import AgentActionType


# ---------------------------------------------------------------------------
# Tool definition schema validation
# ---------------------------------------------------------------------------


class TestToolDefinitions:
    """Every tool must be a valid OpenAI-compatible function definition."""

    def test_nine_tools_defined(self):
        assert len(DECISION_TOOLS) == 9

    def test_all_tools_have_required_fields(self):
        for tool in DECISION_TOOLS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            assert fn["parameters"]["type"] == "object"
            assert "properties" in fn["parameters"]
            assert "required" in fn["parameters"]

    def test_tool_names_match_mapping(self):
        """Every defined tool name must have a mapping in TOOL_TO_ACTION_TYPE."""
        for tool in DECISION_TOOLS:
            name = tool["function"]["name"]
            assert name in TOOL_TO_ACTION_TYPE, f"Missing mapping for tool: {name}"

    def test_mapping_covers_all_action_types(self):
        """Every AgentActionType must have a corresponding tool."""
        mapped_types = set(TOOL_TO_ACTION_TYPE.values())
        for action_type in AgentActionType:
            assert action_type in mapped_types, f"Missing tool for action type: {action_type}"

    def test_flash_sale_has_discount_percent(self):
        """flash_sale tool must produce discount_percent (what _execute_payload reads)."""
        tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_flash_sale")
        props = tool["function"]["parameters"]["properties"]
        assert "product_id" in props
        assert "discount_percent" in props
        assert "discount_percent" in tool["function"]["parameters"]["required"]

    def test_layout_morph_has_new_grid(self):
        """layout_morph tool must produce new_grid (what _execute_payload reads)."""
        tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_layout_morph")
        props = tool["function"]["parameters"]["properties"]
        assert "new_grid" in props
        assert "new_grid" in tool["function"]["parameters"]["required"]

    def test_price_rebalance_has_product_id_and_new_price(self):
        """propose_price_rebalance tool must produce product_id + new_price
        (what agent.py's _register_price_rebalance reads)."""
        tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_price_rebalance")
        props = tool["function"]["parameters"]["properties"]
        assert "product_id" in props
        assert "new_price" in props

    def test_recovery_offer_has_discount_percent(self):
        """recovery_offer tool must produce discount_percent (what _execute_payload reads)."""
        tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_recovery_offer")
        props = tool["function"]["parameters"]["properties"]
        assert "discount_percent" in props

    def test_duplicate_merge_has_keep_and_remove_ids(self):
        """propose_duplicate_merge tool must produce keep_product_id +
        remove_product_ids (what agent.py's _execute_payload reads)."""
        tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_duplicate_merge")
        props = tool["function"]["parameters"]["properties"]
        assert "keep_product_id" in props
        assert "remove_product_ids" in props
        required = tool["function"]["parameters"]["required"]
        assert "keep_product_id" in required
        assert "remove_product_ids" in required

    def test_feature_product_has_product_id_and_label(self):
        """propose_feature_product tool must produce product_id +
        featured_label (what agent.py's _execute_payload reads)."""
        tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_feature_product")
        props = tool["function"]["parameters"]["properties"]
        assert "product_id" in props
        assert "featured_label" in props
        required = tool["function"]["parameters"]["required"]
        assert "product_id" in required
        assert "featured_label" in required

    def test_cart_dwell_nudge_has_discount_percent(self):
        """cart_dwell_nudge tool must produce discount_percent (what
        agent.py's _register_recovery reads via _execute_payload)."""
        tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_cart_dwell_nudge")
        props = tool["function"]["parameters"]["properties"]
        assert "discount_percent" in props


# ---------------------------------------------------------------------------
# Narrative generation
# ---------------------------------------------------------------------------


class TestNarrativeFromTool:
    """Each tool name must produce a well-formed narrative dict."""

    def test_flash_sale_narrative(self):
        result = narrative_from_tool(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": 15, "duration_minutes": 1440},
            "Leather Slides",
            "Velocity spike: 12 views in 30s",
            "warm and confident",
        )
        assert "Flash Sale" in result["title"]
        assert "15%" in result["title"]
        assert "Leather Slides" in result["title"]
        assert "24" in result["description"]  # 1440/60 = 24 hours
        assert result["trigger"] == "Velocity spike: 12 views in 30s"
        assert "warm and confident" in result["brand_check"]

    def test_scarcity_price_narrative(self):
        result = narrative_from_tool(
            "propose_scarcity_price",
            {"product_id": "p2", "discount_percent": 10},
            "Wool Jacket",
            "Velocity spike: 20 views",
        )
        assert "Scarcity" in result["title"]
        assert "Wool Jacket" in result["title"]

    def test_layout_morph_narrative(self):
        result = narrative_from_tool(
            "propose_layout_morph",
            {"new_grid": "masonry-4col"},
            None,  # no product name for layout changes
            "Velocity spike: 8 views",
        )
        assert "masonry-4col" in result["title"]
        assert "Layout" in result["title"]

    def test_recovery_offer_narrative(self):
        result = narrative_from_tool(
            "propose_recovery_offer",
            {"discount_percent": 12},
            None,
            "Cart abandon surge: 7 abandons in 30s",
        )
        assert "Recovery" in result["title"]
        assert "12%" in result["title"]
        assert "cart abandon" in result["description"].lower()

    def test_copy_rewrite_narrative(self):
        result = narrative_from_tool(
            "propose_copy_rewrite",
            {"target": "hero_headline"},
            None,
            "Velocity spike: 10 views",
        )
        assert "Hero Headline" in result["title"]
        assert "hero_headline" in result["description"]

    def test_duplicate_merge_narrative(self):
        result = narrative_from_tool(
            "propose_duplicate_merge",
            {"keep_product_id": "prod_a", "remove_product_ids": ["prod_b", "prod_c"]},
            "Alexander McQueen Logo Strap Slides",
            'Duplicate listings: 3 entries for "Alexander McQueen Logo Strap Slides" — prod_a (...), prod_b (...), prod_c (...) — same product listed under separate entries',
        )
        assert "Duplicate Cleanup" in result["title"]
        assert "Alexander McQueen Logo Strap Slides" in result["title"]
        assert "2" in result["description"]  # 2 removed

    def test_feature_product_narrative(self):
        result = narrative_from_tool(
            "propose_feature_product",
            {"product_id": "prod_new1", "featured_label": "New Arrival"},
            "Leather Slides",
            '"Leather Slides" ($40.00) enters "footwear" — 5 orders there in the last 168h, category averages $40.00',
        )
        assert "Leather Slides" in result["title"]
        assert "New Arrival" in result["description"]

    def test_unknown_tool_fallback(self):
        result = narrative_from_tool(
            "propose_unknown_action",
            {"foo": "bar"},
            "Product X",
            "Some anomaly",
        )
        assert result["title"]  # non-empty
        assert result["trigger"] == "Some anomaly"

    def test_missing_product_name_uses_default(self):
        result = narrative_from_tool(
            "propose_flash_sale",
            {"discount_percent": 20},
            None,
            "test",
        )
        assert "product" in result["title"]  # falls back to "product"

    def test_narrative_has_all_required_keys(self):
        for tool in DECISION_TOOLS:
            name = tool["function"]["name"]
            result = narrative_from_tool(name, {}, "Test Product", "Test anomaly")
            assert "title" in result
            assert "description" in result
            assert "trigger" in result
            assert "brand_check" in result


# ---------------------------------------------------------------------------
# parse_tool_args
# ---------------------------------------------------------------------------


class TestParseToolArgs:
    def test_valid_json(self):
        assert parse_tool_args('{"product_id": "p1", "discount_percent": 15}') == {
            "product_id": "p1",
            "discount_percent": 15,
        }

    def test_invalid_json_returns_empty(self):
        assert parse_tool_args("not json") == {}

    def test_none_returns_empty(self):
        assert parse_tool_args(None) == {}

    def test_empty_string_returns_empty(self):
        assert parse_tool_args("") == {}

    def test_empty_object(self):
        assert parse_tool_args("{}") == {}


# ---------------------------------------------------------------------------
# TOOL_TO_ACTION_TYPE mapping
# ---------------------------------------------------------------------------


class TestToolMapping:
    def test_flash_sale_maps_correctly(self):
        assert TOOL_TO_ACTION_TYPE["propose_flash_sale"] == AgentActionType.FLASH_SALE

    def test_scarcity_price_maps_correctly(self):
        assert TOOL_TO_ACTION_TYPE["propose_scarcity_price"] == AgentActionType.SCARCITY_PRICE

    def test_layout_morph_maps_correctly(self):
        assert TOOL_TO_ACTION_TYPE["propose_layout_morph"] == AgentActionType.LAYOUT_MORPH

    def test_recovery_offer_maps_correctly(self):
        assert TOOL_TO_ACTION_TYPE["propose_recovery_offer"] == AgentActionType.RECOVERY_OFFER

    def test_copy_rewrite_maps_correctly(self):
        assert TOOL_TO_ACTION_TYPE["propose_copy_rewrite"] == AgentActionType.COPY_REWRITE

    def test_duplicate_merge_maps_correctly(self):
        assert TOOL_TO_ACTION_TYPE["propose_duplicate_merge"] == AgentActionType.DUPLICATE_MERGE

    def test_feature_product_maps_correctly(self):
        assert TOOL_TO_ACTION_TYPE["propose_feature_product"] == AgentActionType.FEATURE_PRODUCT


def test_propose_price_rebalance_is_registered():
    from app.services.tools import DECISION_TOOLS, TOOL_TO_ACTION_TYPE
    from app.models.schemas import AgentActionType

    names = [t["function"]["name"] for t in DECISION_TOOLS]
    assert "propose_price_rebalance" in names
    assert TOOL_TO_ACTION_TYPE["propose_price_rebalance"] == AgentActionType.PRICE_REBALANCE

    tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_price_rebalance")
    required = tool["function"]["parameters"]["required"]
    assert "product_id" in required
    assert "new_price" in required
    assert "reasoning_signals" in required


def test_narrative_from_tool_price_rebalance():
    from app.services.tools import narrative_from_tool

    narrative = narrative_from_tool(
        "propose_price_rebalance",
        {"product_id": "p1", "new_price": 24.5, "reasoning_signals": "purchases up 40% at current price"},
        "Leather Slides",
        "Price review: Leather Slides",
    )
    assert "Leather Slides" in narrative["title"]
    assert "24.5" in narrative["title"] or "24.50" in narrative["title"]
    assert "purchases up 40%" in narrative["description"]

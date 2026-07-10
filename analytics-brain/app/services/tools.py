"""
Qwen tool-calling definitions for the decision cycle.

Each tool maps to an AgentActionType. When Qwen calls a tool, the arguments
become the AgentAction.payload dict — the same shape _execute_payload() reads
on approval (discount_percent, duration_minutes, new_grid, etc.).

Narrative fields (title, description, trigger, brand_check) are templated
from the tool call + context, not from Qwen's structured params.
"""

import json
import logging
from app.models.schemas import AgentActionType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI-compatible function-calling format)
# ---------------------------------------------------------------------------

DECISION_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "propose_flash_sale",
            "description": (
                "Create a time-limited flash sale on a specific product "
                "to drive immediate conversions during a velocity spike."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "ID of the product to discount",
                    },
                    "discount_percent": {
                        "type": "number",
                        "description": "Discount percentage, e.g. 15 for 15% off",
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "How long the sale lasts in minutes (default 1440 = 24h)",
                    },
                },
                "required": ["product_id", "discount_percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_scarcity_price",
            "description": (
                "Apply a scarcity discount on a high-demand product with "
                "low stock to accelerate conversions before stockout."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "ID of the high-demand product",
                    },
                    "discount_percent": {
                        "type": "number",
                        "description": "Discount percentage, e.g. 10 for 10% off",
                    },
                },
                "required": ["product_id", "discount_percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_layout_morph",
            "description": (
                "Change the storefront layout variant to better match "
                "current browsing behavior patterns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_grid": {
                        "type": "string",
                        "description": (
                            "Layout variant to switch to. Must be a valid "
                            "LayoutVariant value (e.g. 'masonry-4col', "
                            "'grid-3col', 'carousel-large')."
                        ),
                    },
                },
                "required": ["new_grid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_recovery_offer",
            "description": (
                "Create an order-level recovery discount to combat cart "
                "abandonment. Applied at checkout, NOT free shipping."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "discount_percent": {
                        "type": "number",
                        "description": "Recovery discount percentage, e.g. 12 for 12% off cart total",
                    },
                },
                "required": ["discount_percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_copy_rewrite",
            "description": (
                "Rewrite storefront copy (hero headline, product description, "
                "or section text) to better match current customer behavior."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["hero_headline", "product_description", "section_copy"],
                        "description": "Which copy element to rewrite",
                    },
                    "product_id": {
                        "type": "string",
                        "description": "Product ID if rewriting a specific product description",
                    },
                },
                "required": ["target"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool name → AgentActionType mapping
# ---------------------------------------------------------------------------

TOOL_TO_ACTION_TYPE: dict[str, AgentActionType] = {
    "propose_flash_sale": AgentActionType.FLASH_SALE,
    "propose_scarcity_price": AgentActionType.SCARCITY_PRICE,
    "propose_layout_morph": AgentActionType.LAYOUT_MORPH,
    "propose_recovery_offer": AgentActionType.RECOVERY_OFFER,
    "propose_copy_rewrite": AgentActionType.COPY_REWRITE,
}

# ---------------------------------------------------------------------------
# Narrative generation — templated from tool call + context
# ---------------------------------------------------------------------------


def narrative_from_tool(
    tool_name: str,
    args: dict,
    product_name: str | None,
    anomaly_desc: str,
    brand_voice: str = "",
) -> dict:
    """Generate title, description, trigger, brand_check from a tool call.

    Returns a dict with keys: title, description, trigger, brand_check.
    """
    name = product_name or "product"
    short_anomaly = anomaly_desc.split(":")[0].lower() if anomaly_desc else "behavior signal"
    d = args.get("discount_percent", 10)

    if tool_name == "propose_flash_sale":
        mins = args.get("duration_minutes", 1440)
        hours = round(mins / 60, 1)
        return {
            "title": f"Flash Sale: {d}% off {name}",
            "description": f"{hours}-hour flash sale to capture {short_anomaly}",
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_scarcity_price":
        return {
            "title": f"Scarcity Price: {name} in high demand",
            "description": f"{d}% scarcity discount to protect margin on low stock",
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_layout_morph":
        new_grid = args.get("new_grid", "variant")
        return {
            "title": f"Layout Morph → {new_grid}",
            "description": f"Morph storefront layout to {new_grid} to match browsing pattern",
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_recovery_offer":
        return {
            "title": f"Recovery Offer: {d}% off cart",
            "description": f"Order-level discount to recover {short_anomaly}",
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_copy_rewrite":
        target = args.get("target", "content")
        return {
            "title": f"Copy Rewrite: {target.replace('_', ' ').title()}",
            "description": f"Rewrite {target} to better match current customer behavior",
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    # Fallback for unknown tool names
    logger.warning("Unknown tool name in tool call: %s", tool_name)
    return {
        "title": tool_name.replace("_", " ").title(),
        "description": "Auto-generated action from Qwen tool calling",
        "trigger": anomaly_desc[:200],
        "brand_check": "Auto-generated via tool calling",
    }


def parse_tool_args(raw_arguments: str) -> dict:
    """Safely parse tool call arguments JSON string. Returns {} on failure."""
    if not raw_arguments:
        return {}
    try:
        return json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to parse tool arguments: %s — %s", str(raw_arguments)[:200], e)
        return {}

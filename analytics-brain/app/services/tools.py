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

# A required "reasoning" argument on every tool, not a free-text message
# alongside the tool call. Tool-calling Qwen (like most function-calling
# LLMs) reliably omits `message.content` once it decides to call a
# function — the prompt asking for "step-by-step reasoning in your
# message" was silently unenforceable, leaving the reasoning column empty
# for ~95% of real decisions in production. A required JSON field the
# model must fill to satisfy the tool call schema is reliably populated,
# the same way any other structured Qwen output is (see CLAUDE.md's Qwen
# Output Handling: always structured JSON, never freeform prose).
REASONING_PARAM = {
    "type": "string",
    "description": (
        "Why this action makes sense right now — the specific signal you "
        "observed, and the outcome you expect. Be concrete with numbers."
    ),
}

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
                    "reasoning": REASONING_PARAM,
                },
                "required": ["product_id", "discount_percent", "reasoning"],
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
                    "reasoning": REASONING_PARAM,
                },
                "required": ["product_id", "discount_percent", "reasoning"],
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
                    "reasoning": REASONING_PARAM,
                },
                "required": ["new_grid", "reasoning"],
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
                    "reasoning": REASONING_PARAM,
                },
                "required": ["discount_percent", "reasoning"],
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
                    "reasoning": REASONING_PARAM,
                },
                "required": ["target", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_duplicate_merge",
            "description": (
                "Merge duplicate product listings identified in the anomaly "
                "description into one. Use the EXACT product IDs given in "
                "the anomaly text — do not invent IDs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keep_product_id": {
                        "type": "string",
                        "description": "ID of the listing to keep — the more complete/accurate one",
                    },
                    "remove_product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of the duplicate listings to remove",
                    },
                    "reasoning": REASONING_PARAM,
                },
                "required": ["keep_product_id", "remove_product_ids", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_feature_product",
            "description": (
                "Spotlight a newly-added product to customers likely to "
                "buy it, based on how its category has been performing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "ID of the new product to feature",
                    },
                    "featured_label": {
                        "type": "string",
                        "description": "Short badge text in brand voice, e.g. 'New Arrival' or 'Trending Pick'",
                    },
                    "reasoning": REASONING_PARAM,
                },
                "required": ["product_id", "featured_label", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_price_rebalance",
            "description": (
                "Reprice a single product within your authorized range around its "
                "baseline price, based on its own sales history (or a similar "
                "product's history if it's new). This is NOT a discount — it can "
                "move the live price UP or DOWN from where it is now."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "ID of the product to reprice",
                    },
                    "new_price": {
                        "type": "number",
                        "description": "The new live price to set",
                    },
                    "reasoning_signals": {
                        "type": "string",
                        "description": (
                            "The specific signals driving this call, e.g. "
                            "'purchases up 40% at current price, comparable product "
                            "X sustained a +8% price with no drop in conversion'"
                        ),
                    },
                },
                "required": ["product_id", "new_price", "reasoning_signals"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_cart_dwell_nudge",
            "description": (
                "Nudge a customer whose cart has sat untouched for a while but "
                "who hasn't left yet — an order-level discount to encourage "
                "completing checkout now, before they abandon."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "discount_percent": {
                        "type": "number",
                        "description": "Nudge discount percentage, e.g. 8 for 8% off cart total",
                    },
                    "reasoning": REASONING_PARAM,
                },
                "required": ["discount_percent", "reasoning"],
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
    "propose_duplicate_merge": AgentActionType.DUPLICATE_MERGE,
    "propose_feature_product": AgentActionType.FEATURE_PRODUCT,
    "propose_price_rebalance": AgentActionType.PRICE_REBALANCE,
    "propose_cart_dwell_nudge": AgentActionType.CART_DWELL_NUDGE,
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
            "title": f"Flash Sale: {d:g}% off {name}",
            "description": f"{hours}-hour flash sale to capture {short_anomaly}",
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_scarcity_price":
        return {
            "title": f"Scarcity Price: {name} in high demand",
            "description": f"{d:g}% scarcity discount to protect margin on low stock",
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
            "title": f"Recovery Offer: {d:g}% off cart",
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

    if tool_name == "propose_duplicate_merge":
        n_removed = len(args.get("remove_product_ids") or [])
        return {
            "title": f"Duplicate Cleanup: {name}",
            "description": f"Merge {n_removed} duplicate listing(s) into one — keeps the most complete version",
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_feature_product":
        label = args.get("featured_label", "New Arrival")
        return {
            "title": f"Feature: {name}",
            "description": f'Spotlight "{name}" as "{label}" — likely to convert based on category performance',
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_price_rebalance":
        new_price = args.get("new_price", 0)
        signals = args.get("reasoning_signals", "Repricing based on recent sales history")
        return {
            "title": f"Price Rebalance: {name} → ${new_price:.2f}",
            "description": str(signals)[:300],
            "trigger": anomaly_desc[:200],
            "brand_check": f"Aligned with {brand_voice} voice" if brand_voice else "Auto-generated via tool calling",
        }

    if tool_name == "propose_cart_dwell_nudge":
        return {
            "title": f"Cart Nudge: {d:g}% off to complete checkout",
            "description": f"Order-level nudge for a cart that's gone quiet — {short_anomaly}",
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

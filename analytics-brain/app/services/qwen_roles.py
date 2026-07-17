"""
Qwen "swarm" — named, scoped roles instead of one generalist prompt with all
nine DECISION_TOOLS available to every trigger. Each role owns a disjoint
subset of tools and gets its own system-prompt framing; routing a trigger to
a role is a relabeling of existing dispatch (run_decision_cycle already
accepts a scoped `tools` list and a custom prompt — see pricing_cycle.py's
own precedent for PRICE_REBALANCE) rather than new infrastructure. Same one
Qwen call per triggered event either way — no added token cost.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.tools import DECISION_TOOLS


@dataclass(frozen=True)
class QwenRole:
    name: str
    mission_line: str  # {store_name} placeholder — becomes DECISION_PROMPT's opening line
    tool_names: tuple[str, ...]
    default_priority: int  # baseline for the priority-arbitration gate — see learning.compute_effective_priority


PRICING_STRATEGIST = QwenRole(
    name="pricing_strategist",
    mission_line=(
        'You are the Pricing Strategist for "{store_name}" — you own live '
        "pricing, flash sales, and scarcity pricing. Your only job is "
        "protecting margin while capturing real demand; you never touch "
        "layout, copy, or catalog hygiene."
    ),
    tool_names=("propose_flash_sale", "propose_scarcity_price", "propose_price_rebalance"),
    default_priority=20,
)

SALES_REP = QwenRole(
    name="sales_rep",
    mission_line=(
        'You are the Sales Rep for "{store_name}" — you own recovering '
        "abandoned carts, nudging dwelling ones, and spotlighting new "
        "arrivals. Your only job is converting real buying intent into "
        "completed orders; you never touch pricing, layout, or catalog "
        "hygiene."
    ),
    tool_names=("propose_recovery_offer", "propose_cart_dwell_nudge", "propose_feature_product"),
    default_priority=30,
)

INVENTORY_OVERSEER = QwenRole(
    name="inventory_overseer",
    mission_line=(
        'You are the Inventory Overseer for "{store_name}" — you own '
        "catalog hygiene. Your only job is spotting and merging duplicate "
        "listings so the catalog stays clean and trustworthy; you never "
        "touch pricing, layout, or copy."
    ),
    tool_names=("propose_duplicate_merge",),
    default_priority=10,
)

STORE_CURATOR = QwenRole(
    name="store_curator",
    mission_line=(
        'You are the Store Curator for "{store_name}" — you own '
        "storefront presentation: layout variants and copy. Your only job "
        "is making sure a product with real interest but no conversions is "
        "presented in a way that actually sells; you never touch pricing "
        "or catalog hygiene."
    ),
    tool_names=("propose_layout_morph", "propose_copy_rewrite"),
    default_priority=10,
)

ALL_ROLES: tuple[QwenRole, ...] = (PRICING_STRATEGIST, SALES_REP, INVENTORY_OVERSEER, STORE_CURATOR)


def get_role_tools(role: QwenRole) -> list[dict]:
    """DECISION_TOOLS filtered to this role's tool_names, in DECISION_TOOLS'
    own order. Pure — no I/O."""
    names = set(role.tool_names)
    return [t for t in DECISION_TOOLS if t["function"]["name"] in names]


_ACTION_TYPE_TO_TOOL = {
    "flash_sale": "propose_flash_sale",
    "scarcity_price": "propose_scarcity_price",
    "layout_morph": "propose_layout_morph",
    "recovery_offer": "propose_recovery_offer",
    "copy_rewrite": "propose_copy_rewrite",
    "duplicate_merge": "propose_duplicate_merge",
    "feature_product": "propose_feature_product",
    "price_rebalance": "propose_price_rebalance",
    "cart_dwell_nudge": "propose_cart_dwell_nudge",
}


def role_for_action_type(action_type: str) -> str | None:
    """Reverse lookup: AgentActionType string -> role name. Used to backfill
    a display label for any AgentActionDB row that predates the role column
    (role=None in the DB) — see Task 6. Pure — no I/O."""
    tool_name = _ACTION_TYPE_TO_TOOL.get(action_type)
    if tool_name is None:
        return None
    for role in ALL_ROLES:
        if tool_name in role.tool_names:
            return role.name
    return None


def role_for_anomaly(desc: str) -> QwenRole:
    """behavior.py's two reactive triggers (velocity spike, cart abandon
    surge) share one anomaly_description() call — this maps its two known
    literal prefixes to a role. Raises ValueError on an unrecognized prefix
    rather than silently guessing, matching this codebase's general
    preference for failing loud over failing quiet (see e.g.
    tools.py's "unknown tool name" warning-and-fallback being the one
    deliberate exception, logged loudly)."""
    if desc.startswith("Cart abandon surge"):
        return SALES_REP
    if desc.startswith("Velocity spike"):
        return PRICING_STRATEGIST
    raise ValueError(f"no role mapping for anomaly description: {desc!r}")


def role_by_name(name: str | None) -> QwenRole | None:
    """Reverse lookup: role name string -> the QwenRole object, or None if
    name is None or unrecognized. Used wherever a persisted role name (e.g.
    AgentActionDB.role, or a name string parsed from a tool call) needs to
    become a real QwenRole to read its own fields (default_priority,
    can_escalate_to). Pure — no I/O."""
    if name is None:
        return None
    return next((r for r in ALL_ROLES if r.name == name), None)

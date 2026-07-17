"""Per-role learning — the measurable, visible half of the cognitive loop.

memory.py already remembers *what happened* (prose outcomes injected into the
prompt). This module answers the sharper question: given how this specific
merchant has resolved a role's past proposals, *what should that role do
differently next time* — expressed as a quantified stance, not a vibe.

For each QwenRole we aggregate the store's resolved AgentAction history for that
role's action types into a RoleLearning: how many proposals were kept vs
dismissed, and — for discount-bearing roles — the discount level the merchant
keeps vs the level they reject. render_learned_stance turns that into one
directive line injected into the role's next prompt, so proposals measurably
converge on what the store actually accepts. The same numbers ride the decision
`context_snapshot`, so the shift is visible on the Decision Trace page.

No Qwen call, no extra tokens — the stance rides the existing single decision
call. A stateless one-shot agent cannot produce any of this; it has no history.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services.qwen_roles import QwenRole

# Below this many *resolved* proposals we make no claim — an honest agent
# doesn't lecture a store about a pattern it hasn't seen yet (and we waste no
# prompt tokens on an empty stance, matching build_memory_context).
MIN_SIGNAL = 3

# A discount gap smaller than this (percentage points) between kept and
# dismissed offers is noise, not a signal — don't emit a "lead with" directive.
_MEANINGFUL_GAP = 3.0

_APPROVED_STATUS = {"approved", "executed"}
_APPROVED_BEHAVIOR = {"approved", "approved_then_modified"}
_DISMISSED = {"dismissed"}


@dataclass(frozen=True)
class RoleLearning:
    role: str
    n_approved: int
    n_dismissed: int
    approved_avg_discount: Optional[float]
    dismissed_avg_discount: Optional[float]

    @property
    def n_resolved(self) -> int:
        return self.n_approved + self.n_dismissed

    @property
    def approval_rate(self) -> float:
        return self.n_approved / self.n_resolved if self.n_resolved else 0.0

    @property
    def has_signal(self) -> bool:
        return self.n_resolved >= MIN_SIGNAL


def _classify(rec: dict) -> Optional[str]:
    """'approved' | 'dismissed' | None (pending / blocked — not a merchant
    judgment, so it teaches us nothing)."""
    status = (rec.get("status") or "").lower()
    behavior = (rec.get("merchant_behavior") or "").lower()
    if status in _DISMISSED or behavior in _DISMISSED:
        return "dismissed"
    if status in _APPROVED_STATUS or behavior in _APPROVED_BEHAVIOR:
        return "approved"
    return None


def _discount(rec: dict) -> Optional[float]:
    val = (rec.get("payload") or {}).get("discount_percent")
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _avg(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 2) if values else None


def compute_role_learning(records: list[dict], role_name: str) -> RoleLearning:
    """Aggregate a role's resolved-action records (dicts with `status`,
    `merchant_behavior`, `payload`) into a RoleLearning. Pure — no I/O."""
    approved_discounts: list[float] = []
    dismissed_discounts: list[float] = []
    n_approved = n_dismissed = 0
    for rec in records:
        verdict = _classify(rec)
        if verdict is None:
            continue
        d = _discount(rec)
        if verdict == "approved":
            n_approved += 1
            if d is not None:
                approved_discounts.append(d)
        else:
            n_dismissed += 1
            if d is not None:
                dismissed_discounts.append(d)
    return RoleLearning(
        role=role_name,
        n_approved=n_approved,
        n_dismissed=n_dismissed,
        approved_avg_discount=_avg(approved_discounts),
        dismissed_avg_discount=_avg(dismissed_discounts),
    )


def render_learned_stance(learning: RoleLearning) -> str:
    """One compact directive line for the role's prompt, or "" when there
    isn't enough resolved history to say anything honest."""
    if not learning.has_signal:
        return ""
    parts = [
        f"Learned for this store: the merchant has kept {learning.n_approved} of "
        f"{learning.n_resolved} recent {learning.role} proposals."
    ]
    ad, dd = learning.approved_avg_discount, learning.dismissed_avg_discount
    if ad is not None and dd is not None and (dd - ad) >= _MEANINGFUL_GAP:
        parts.append(
            f"Kept offers averaged {ad:.0f}% off vs {dd:.0f}% for dismissed ones — "
            f"lead with about {ad:.0f}%."
        )
    elif learning.approval_rate >= 0.75:
        parts.append("They tend to accept these — stay the course.")
    elif learning.approval_rate <= 0.34:
        parts.append("They dismiss most of these — only propose on a clearly strong signal.")
    return " ".join(parts)


def compute_effective_priority(default_priority: int, learning: Optional[RoleLearning]) -> int:
    """A QwenRole's own default_priority (see qwen_roles.py), adjusted by this
    merchant's own per-role learning for the priority-arbitration gate in
    decision_engine.run_decision_cycle. Reuses THIS module's own signal
    threshold (has_signal / MIN_SIGNAL) and approval-rate boundaries (0.75 /
    0.34 — the same numbers render_learned_stance's own "stay the course" /
    "only propose on a clearly strong signal" branches already use) rather
    than inventing a second, slightly different notion of "enough history"
    and "high/low approval" alongside them.

    +10 if learning.has_signal and approval_rate >= 0.75.
    -10 if learning.has_signal and approval_rate <= 0.34.
    Otherwise (no learning passed, not enough signal yet, or a mixed rate)
    stays at default_priority. Pure — no I/O; takes a plain int rather than
    a QwenRole so this module has zero dependency on qwen_roles.py."""
    if learning is None or not learning.has_signal:
        return default_priority
    if learning.approval_rate >= 0.75:
        return default_priority + 10
    if learning.approval_rate <= 0.34:
        return default_priority - 10
    return default_priority


async def load_role_learning(merchant_id: str, role: "QwenRole", db: "AsyncSession") -> RoleLearning:
    """DB glue: pull this role's action history for the store and aggregate it.
    Thin wrapper over compute_role_learning — the logic lives there."""
    from sqlalchemy import select
    from app.models.db_models import AgentActionDB
    from app.services.tools import TOOL_TO_ACTION_TYPE

    action_types = {
        TOOL_TO_ACTION_TYPE[t].value
        for t in role.tool_names
        if t in TOOL_TO_ACTION_TYPE
    }
    if not action_types:
        return compute_role_learning([], role.name)

    rows = (
        await db.execute(
            select(AgentActionDB)
            .where(AgentActionDB.merchant_id == merchant_id)
            .where(AgentActionDB.action_type.in_(action_types))
            .order_by(AgentActionDB.created_at)
        )
    ).scalars().all()
    records = [
        {"status": r.status, "merchant_behavior": r.merchant_behavior, "payload": r.payload}
        for r in rows
    ]
    return compute_role_learning(records, role.name)

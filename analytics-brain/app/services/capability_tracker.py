"""Self-extending config surface.

When a merchant's point-and-edit intent can't be satisfied by any existing DSL
option, we log the *capability* they were reaching for. If the same capability
recurs (>= PROPOSE_THRESHOLD), Qwen proposes adding it as a NEW store config
dimension — the system notices its own gaps and grows. Stored on
merchants.capability_requests JSONB (durable); Redis is just a hot mirror.
"""
from __future__ import annotations

import re
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PROPOSE_THRESHOLD = 2  # ask once; on the 2nd identical gap, propose adding it


def slugify_capability(label: str) -> str:
    """Canonicalize a free-text capability into a stable key so repeats collide."""
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return s[:48] or "unknown-capability"


async def record_unmet(
    merchant_id: str, capability_label: str, intent: str, db: "AsyncSession",
) -> dict:
    """Increment the count for this capability. Returns
    {capability, count, proposed} where proposed flips true once the same gap
    has been seen PROPOSE_THRESHOLD times."""
    from app.models.db_models import MerchantDB

    m = await db.get(MerchantDB, merchant_id)
    if not m:
        return {"capability": slugify_capability(capability_label), "count": 1, "proposed": False}

    key = slugify_capability(capability_label)
    reqs = dict(m.capability_requests or {})
    entry = reqs.get(key) or {"count": 0, "label": capability_label, "status": "open"}
    entry["count"] = int(entry.get("count", 0)) + 1
    entry["label"] = capability_label
    entry["last_intent"] = intent[:200]
    entry["last_at"] = int(time.time() * 1000)
    proposed = entry["count"] >= PROPOSE_THRESHOLD
    if proposed and entry.get("status") == "open":
        entry["status"] = "proposed"
    reqs[key] = entry
    m.capability_requests = reqs        # reassign so SQLAlchemy flags JSON dirty
    await db.commit()

    logger.info("[capability] %s wants %r (count=%d proposed=%s)", merchant_id, key, entry["count"], proposed)
    return {"capability": key, "label": capability_label, "count": entry["count"], "proposed": proposed}


async def list_capabilities(merchant_id: str, db: "AsyncSession") -> list[dict]:
    """All tracked capability gaps for a store, most-requested first."""
    from app.models.db_models import MerchantDB
    m = await db.get(MerchantDB, merchant_id)
    if not m or not m.capability_requests:
        return []
    out = [
        {"capability": k, "label": v.get("label", k), "count": int(v.get("count", 0)),
         "status": v.get("status", "open"), "last_intent": v.get("last_intent", "")}
        for k, v in m.capability_requests.items()
    ]
    return sorted(out, key=lambda x: x["count"], reverse=True)

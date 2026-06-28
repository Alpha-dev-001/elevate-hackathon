"""Per-store Qwen memory — the cognitive loop's storage layer.

After an action resolves, the outcome observer writes a MemoryEntry here. Every
subsequent decision cycle reads the recent entries back via build_memory_context
and injects them into the prompt, so Qwen gets genuinely smarter per store.

Redis (`merchant_memory:{id}`) is the fast layer; Postgres `merchants.qwen_memory`
is the durable copy. Redis is best-effort — a flush never loses memory.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING

from app.models.schemas import MemoryEntry

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MEMORY_CONTEXT_ENTRIES = int(os.getenv("MEMORY_CONTEXT_ENTRIES", "8"))
_MAX_STORED = 20


def _redis_key(merchant_id: str) -> str:
    return f"merchant_memory:{merchant_id}"


def build_memory_context(entries: list[MemoryEntry], limit: int = MEMORY_CONTEXT_ENTRIES) -> str:
    """Render the last `limit` entries into a compact prompt block. Empty when
    there is nothing to remember (no wasted tokens)."""
    if not entries:
        return ""
    recent = entries[-limit:]
    lines = [
        f"[{e.timestamp.date()}] {e.action_type}: {e.trigger} → {e.outcome} (merchant: {e.merchant_behavior})"
        for e in recent
    ]
    return "What I know about this store:\n" + "\n".join(lines)


async def get_memory(merchant_id: str, db: "AsyncSession", redis: "Redis | None" = None) -> list[MemoryEntry]:
    """Redis first (fast), Postgres fallback (durable)."""
    if redis is not None:
        try:
            raw = await redis.get(_redis_key(merchant_id))
            if raw:
                data = json.loads(raw)
                return [MemoryEntry.model_validate(e) for e in data]
        except Exception as e:  # noqa: BLE001
            logger.warning("[memory] redis read failed for %s: %s", merchant_id, e)

    from app.models.db_models import MerchantDB
    m = await db.get(MerchantDB, merchant_id)
    if not m or not m.qwen_memory:
        return []
    entries = (m.qwen_memory or {}).get("entries", [])
    out: list[MemoryEntry] = []
    for e in entries:
        try:
            out.append(MemoryEntry.model_validate(e))
        except Exception:  # noqa: BLE001 — skip a single corrupt entry
            continue
    return out


async def write_memory(merchant_id: str, entry: MemoryEntry, db: "AsyncSession", redis: "Redis | None" = None) -> None:
    """Append an entry, cap at the last _MAX_STORED, write Postgres (durable)
    then mirror to Redis (best-effort)."""
    from app.models.db_models import MerchantDB
    m = await db.get(MerchantDB, merchant_id)
    if not m:
        logger.warning("[memory] write skipped — no merchant %s", merchant_id)
        return

    existing = (m.qwen_memory or {}).get("entries", [])
    existing.append(json.loads(entry.model_dump_json()))
    existing = existing[-_MAX_STORED:]
    m.qwen_memory = {"entries": existing}
    await db.commit()

    if redis is not None:
        try:
            await redis.set(_redis_key(merchant_id), json.dumps(existing))
        except Exception as e:  # noqa: BLE001
            logger.warning("[memory] redis mirror failed for %s: %s", merchant_id, e)

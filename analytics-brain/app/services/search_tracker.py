"""Store-wide search-demand tracking.

The storefront search box filters store.products entirely client-side (the
full catalog is already in memory — no round trip needed for the filter
itself, same reasoning as the category chips). This service exists purely
to LOG each search query so the merchant — and eventually Qwen's proactive
review — can see what customers are actually asking for, especially
searches that matched nothing: real, aggregated demand signal for products
the store doesn't carry. Deterministic counting only, no Qwen call per
search (a live per-keystroke or per-search model call would violate the
token-efficiency rule against throwaway calls and blow the <2s interactive
budget for no reason — this is exactly the kind of signal that's cheap to
count and only worth reasoning over in aggregate).

Stored on merchants.search_queries JSONB — same shape and precedent as
capability_tracker.py's capability_requests.
"""
from __future__ import annotations

import re
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# A query needs to carry real intent to be worth counting — single characters
# and typing-in-progress fragments would just add noise to the merchant's
# insight list.
MIN_QUERY_LENGTH = 2


def slugify_query(query: str) -> str:
    """Canonicalize a free-text search into a stable key so repeats collide
    (same normalization approach as capability_tracker.slugify_capability)."""
    s = re.sub(r"[^a-z0-9]+", "-", (query or "").lower()).strip("-")
    return s[:48] or "unknown-query"


async def record_search(
    merchant_id: str, query: str, matched: bool, db: "AsyncSession",
) -> dict | None:
    """Increment the count for this search query. Returns None for
    queries too short to be meaningful. `matched` is whether the client-side
    filter found at least one product for this query."""
    from app.models.db_models import MerchantDB

    query = (query or "").strip()
    if len(query) < MIN_QUERY_LENGTH:
        return None

    m = await db.get(MerchantDB, merchant_id)
    if not m:
        return None

    key = slugify_query(query)
    reqs = dict(m.search_queries or {})
    # dict(...) copy is required, not just reqs.get(key) — `reqs` is only a
    # SHALLOW copy of m.search_queries, so its nested values are the exact
    # same dict objects still referenced by m.search_queries[key]. Mutating
    # that shared object in place (instead of a fresh copy) silently
    # corrupts the OLD attribute value too, so SQLAlchemy's dirty-check sees
    # old == new on reassignment and skips the UPDATE entirely — every call
    # after the first for the same query becomes a silent no-op. Reproduced
    # live: two identical POSTs left count=1 in Postgres, not 2.
    entry = dict(reqs.get(key) or {"count": 0, "query": query, "matched": matched})
    entry["count"] = int(entry.get("count", 0)) + 1
    entry["query"] = query
    # Once a query has ever matched, treat it as a matched query — a
    # temporarily out-of-stock item shouldn't get permanently mislabeled
    # as "unmet demand" just because of one earlier miss.
    entry["matched"] = bool(entry.get("matched")) or matched
    entry["last_at"] = int(time.time() * 1000)
    reqs[key] = entry
    m.search_queries = reqs  # reassign so SQLAlchemy flags JSON dirty
    await db.commit()

    logger.info(
        "[search] %s searched %r (count=%d matched=%s)",
        merchant_id, key, entry["count"], entry["matched"],
    )
    return {"query": key, "label": query, "count": entry["count"], "matched": entry["matched"]}


async def list_search_insights(merchant_id: str, db: "AsyncSession") -> list[dict]:
    """All tracked search queries for a store, most-searched first. Each
    entry flags whether it ever matched a product — unmatched, high-count
    queries are the highest-signal insight (real demand for something the
    store doesn't carry)."""
    from app.models.db_models import MerchantDB
    m = await db.get(MerchantDB, merchant_id)
    if not m or not m.search_queries:
        return []
    out = [
        {
            "query": k,
            "label": v.get("query", k),
            "count": int(v.get("count", 0)),
            "matched": bool(v.get("matched", True)),
            "last_at": int(v.get("last_at", 0)),
        }
        for k, v in m.search_queries.items()
    ]
    return sorted(out, key=lambda x: x["count"], reverse=True)

"""
Duplicate detection as the 5th autopilot trigger. Two existing endpoints
(products.py's /deduplicate and /catalog-audit) already contain dedup
*logic* but neither runs automatically — this module makes it a real
signal-driven trigger through the same run_decision_cycle pipeline as
reactive/recovery/proactive store review.

Detection is cheapest-first: free exact-image-URL grouping runs before any
Qwen call; a narrow, dedicated semantic-duplicate prompt only fires if that
finds nothing. Full design:
docs/superpowers/specs/2026-07-12-duplicate-detection-autopilot-design.md
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections import defaultdict
from typing import TYPE_CHECKING

from app.models.db_models import ProductDB, MerchantDB

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.schemas import AgentAction

logger = logging.getLogger(__name__)

# Env-configurable, same pattern as STORE_REVIEW_* in store_review.py.
DUPLICATE_DISMISS_TTL_SECONDS = int(os.getenv("DUPLICATE_DISMISS_TTL_SECONDS", str(7 * 24 * 3600)))


def group_by_primary_image(products: list[ProductDB]) -> dict[str, list[ProductDB]]:
    """Group products by their primary (first) image URL. Groups of size 1
    are not duplicates — callers filter on len(group) >= 2. Pure — no I/O,
    shared by both /deduplicate (products.py) and the periodic scan below
    so the two can never drift apart."""
    by_image: dict[str, list[ProductDB]] = defaultdict(list)
    for p in products:
        if p.image_urls:
            primary = p.image_urls[0]
            if primary:
                by_image[primary].append(p)
    return dict(by_image)


def format_duplicate_description(group: list[ProductDB]) -> str:
    """Count leads the sentence — same digit-safety discipline as
    store_review.format_review_description, so decision_engine._extract_count()
    greps the duplicate count, not a stray digit from a name or ID.

    Product IDs are embedded directly: decision_engine's DECISION_PROMPT only
    ever passes product name/price/stock in products_summary, never IDs, so
    without this, propose_duplicate_merge's tool call would have no real ID
    to put in keep_product_id/remove_product_ids. Mirrors how the reactive
    trigger's anomaly text already embeds the spiking product's ID
    (behavior_tracker.anomaly_description) for the same reason.
    """
    name = group[0].name
    ids = ", ".join(f"{p.id} ({p.name})" for p in group)
    return (
        f'Duplicate listings: {len(group)} entries for "{name}" — {ids} '
        f"— same product listed under separate entries"
    )


def _duplicate_group_hash(product_ids: list[str]) -> str:
    """Stable, order-independent hash of a duplicate group's product IDs —
    keys the dismiss-suppression Redis entry so the exact same group isn't
    re-proposed within the TTL after a merchant dismisses it. Note: computed
    from whatever ID list is available at each call site (the full detected
    group at check time, keep_product_id + remove_product_ids at dismiss
    time) — if Qwen's tool call ever omits a member of the originally
    detected group, the two hashes won't match and suppression won't catch
    that partial case. Accepted: re-proposing the leftover member next tick
    is arguably correct (it IS still an unresolved duplicate), not a bug."""
    return hashlib.sha1(",".join(sorted(product_ids)).encode()).hexdigest()[:16]

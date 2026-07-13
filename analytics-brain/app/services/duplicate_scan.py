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


async def suppress_duplicate_group(merchant_id: str, product_ids: list[str], redis) -> None:
    """Called on dismiss (see agent.py:dismiss_action) — blocks this exact
    group from re-proposing for DUPLICATE_DISMISS_TTL_SECONDS. Not
    permanent: a single dismiss (possibly a misclick) must not blacklist a
    group forever — see the frontend confirm/undo snackbar (OptionCard.tsx)
    for the other half of that protection."""
    from app.core.redis import Keys
    key = Keys.duplicate_dismissed(merchant_id, _duplicate_group_hash(product_ids))
    await redis.set(key, "1", ex=DUPLICATE_DISMISS_TTL_SECONDS)


async def _is_suppressed(merchant_id: str, product_ids: list[str], redis) -> bool:
    from app.core.redis import Keys
    key = Keys.duplicate_dismissed(merchant_id, _duplicate_group_hash(product_ids))
    return bool(await redis.get(key))


DUPLICATE_SCAN_PROMPT = """You are auditing an e-commerce catalog for duplicate product listings — the SAME physical item listed more than once (e.g. two separate photo sessions of one product uploaded as separate entries).

Do NOT flag:
- Two different products that happen to be similar
- The same product in different colors or variants — a color/variant is a different listing, not a duplicate

Store: {store_name} ({category})

Products:
{products_json}

Return ONLY a JSON object:
{{
  "duplicate_group": {{
    "product_ids": ["<id1>", "<id2>"],
    "reasoning": "<why these are the same item listed twice>"
  }}
}}

If you find multiple duplicate groups, return only the single most obvious one. If the catalog has no duplicates, return {{"duplicate_group": null}}."""


async def _find_semantic_duplicate(
    merchant: "MerchantDB", products: list[ProductDB]
) -> tuple[list[str], str] | None:
    """One narrow Qwen call — only reached when the free exact-URL check
    (find_duplicate_group) found nothing. Deliberately does NOT reuse the
    full 5-issue-type catalog-audit prompt; that would burn tokens on 4
    issue types this trigger doesn't care about."""
    import json as _json
    from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError
    from app.core.config import get_settings

    products_json = _json.dumps([
        {"id": p.id, "name": p.name, "description": (p.description or "")[:200]}
        for p in products
    ], ensure_ascii=False)
    prompt = DUPLICATE_SCAN_PROMPT.format(
        store_name=merchant.store_name,
        category=merchant.category,
        products_json=products_json,
    )

    try:
        raw = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.2,
            timeout=30.0,
            merchant_id=merchant.id,
            step="duplicate_scan",
        )
        data = _extract_json(raw)
    except BrandGenerationError as e:
        logger.warning("[duplicate_scan] semantic scan failed for %s: %s", merchant.id, e)
        return None
    except Exception as e:  # noqa: BLE001 — a bad Qwen response must not break the tick
        logger.warning("[duplicate_scan] semantic scan errored for %s: %s", merchant.id, e)
        return None

    group = data.get("duplicate_group") if isinstance(data, dict) else None
    if not isinstance(group, dict):
        return None
    valid_ids = {p.id for p in products}
    product_ids = [pid for pid in (group.get("product_ids") or []) if pid in valid_ids]
    if len(product_ids) < 2:
        return None
    matched = [p for p in products if p.id in product_ids]
    return product_ids, format_duplicate_description(matched)


async def find_duplicate_group(
    merchant_id: str, db: "AsyncSession"
) -> tuple[list[str], str] | None:
    """Detection, cheapest-first. Returns (product_ids, description) for a
    merchant-written exact-URL group or a Qwen-identified semantic group, or
    None if the catalog looks clean. Side effect: silently auto-resolves any
    all-Qwen-generated exact-URL groups along the way — hard-delete,
    matching /deduplicate's existing zero-judgment-call behavior, unchanged
    (this is real autopilot behavior too, it just never produces a card)."""
    from sqlalchemy import select

    rows = await db.scalars(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant_id)
        .where(ProductDB.is_active == True)
    )
    products = list(rows)
    if len(products) < 2:
        return None

    groups = group_by_primary_image(products)
    merchant_written_group: list[ProductDB] | None = None
    auto_deleted_ids: set[str] = set()

    for group in groups.values():
        if len(group) < 2:
            continue
        if all(p.qwen_generated_description for p in group):
            for dup in group[1:]:
                await db.delete(dup)
                auto_deleted_ids.add(dup.id)
            continue
        if merchant_written_group is None:
            merchant_written_group = group

    if auto_deleted_ids:
        await db.flush()
        try:
            from app.routers.products import _sync_state_if_live
            await _sync_state_if_live(db, merchant_id)
        except Exception as e:  # noqa: BLE001 — sync failure must not break detection
            logger.warning(
                "[duplicate_scan] state sync failed after auto-resolve for %s: %s",
                merchant_id, e,
            )

    if merchant_written_group:
        ids = [p.id for p in merchant_written_group]
        return ids, format_duplicate_description(merchant_written_group)

    remaining = [p for p in products if p.id not in auto_deleted_ids]
    if len(remaining) < 2:
        return None

    merchant = await db.get(MerchantDB, merchant_id)
    if not merchant:
        return None
    return await _find_semantic_duplicate(merchant, remaining)


async def run_duplicate_scan(
    merchant_id: str, db: "AsyncSession", redis
) -> "AgentAction | None":
    """Thin async wrapper, mirrors store_review.run_store_review exactly:
    find a candidate, check suppression, run it through the same decision
    cycle as every other trigger. Returns None (not an error) when the
    catalog looks clean, has no card-worthy candidate, or the candidate is
    currently suppressed after a merchant dismissal."""
    found = await find_duplicate_group(merchant_id, db)
    if not found:
        return None
    product_ids, description = found

    if await _is_suppressed(merchant_id, product_ids, redis):
        logger.info(
            "[duplicate_scan] candidate group suppressed (dismissed recently) for %s",
            merchant_id,
        )
        return None

    from app.services.decision_engine import run_decision_cycle
    return await run_decision_cycle(merchant_id, description, db, redis)

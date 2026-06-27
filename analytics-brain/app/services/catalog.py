"""
Qwen observes the catalog (Sprint 2 — observe only, never act).

One batched qwen-max call reviews names, categories and prices and flags
possible pricing issues (an item that reads underpriced for its category, an
outlier, an inconsistent tier). It is strictly advisory: the merchant sees it,
nothing is ever auto-applied. Autonomy is Sprint 3.

Privacy: we send names/categories/prices ONLY. Never cost_price, never margin,
never any customer/PII. The model can't leak what it never receives.

Result is cached in Redis (re-run on demand) so repeat views cost zero tokens.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis import get_redis, Keys, TTL
from app.models.schemas import CatalogReview, PricingFlag
from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError
from app.services.pricing import now_ms
from app.services.products import load_products

logger = logging.getLogger(__name__)


_REVIEW_PROMPT = """You are a pricing analyst reviewing an online store's catalog.

You receive a list of products: id, name, category, price. You do NOT see costs
or margins — judge only on positioning, category norms, and internal consistency.

Flag products with a possible pricing issue. Be conservative: only flag what
genuinely looks off. A clean catalog returns an empty flags array.

Return ONLY this JSON object — no prose, no markdown:
{
  "summary": "one sentence overall read of the catalog's pricing",
  "flags": [
    {
      "product_id": "the exact id from the input",
      "name": "the product name",
      "severity": "low | medium | high",
      "issue": "what looks off, one sentence",
      "suggestion": "what to consider — advisory only, one sentence"
    }
  ]
}

Reference real product ids from the input. Pure JSON. Nothing else."""


async def get_cached_review(merchant_id: str) -> CatalogReview | None:
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.catalog_review(merchant_id))
        if raw:
            return CatalogReview.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"[catalog] cached review read failed for {merchant_id}: {e}")
    return None


async def review_catalog(db: AsyncSession, merchant_id: str) -> CatalogReview:
    """Run (or re-run) the qwen-max catalog review and cache it. Never raises on
    a Qwen failure — degrades to an empty, honest review so the UI never breaks."""
    products = await load_products(db, merchant_id)
    valid_ids = {p.id for p in products}

    if not products:
        review = CatalogReview(
            flags=[], summary="No products to review yet.",
            reviewed_count=0, generated_at=now_ms(),
        )
        await _cache(merchant_id, review)
        return review

    catalogue = [
        {"id": p.id, "name": p.name, "category": p.category or "general", "price": p.price}
        for p in products
    ]

    try:
        raw = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[
                {"role": "system", "content": _REVIEW_PROMPT},
                {"role": "user", "content": json.dumps(catalogue, ensure_ascii=False)},
            ],
            max_tokens=min(4000, 80 * len(products) + 400),
            temperature=0.3,
            timeout=60.0,
        )
        data = _extract_json(raw)
    except BrandGenerationError as e:
        logger.warning(f"[catalog] review failed for {merchant_id}: {e}")
        review = CatalogReview(
            flags=[],
            summary="Pricing review is unavailable right now — try again shortly.",
            reviewed_count=len(products),
            generated_at=now_ms(),
        )
        await _cache(merchant_id, review)
        return review

    flags: list[PricingFlag] = []
    for raw_flag in data.get("flags", []) or []:
        if not isinstance(raw_flag, dict):
            continue
        pid = str(raw_flag.get("product_id", ""))
        if pid not in valid_ids:
            continue  # never trust a hallucinated id
        sev = raw_flag.get("severity", "low")
        if sev not in ("low", "medium", "high"):
            sev = "low"
        flags.append(
            PricingFlag(
                product_id=pid,
                name=str(raw_flag.get("name", "")),
                severity=sev,
                issue=str(raw_flag.get("issue", "")).strip(),
                suggestion=str(raw_flag.get("suggestion", "")).strip(),
            )
        )

    review = CatalogReview(
        flags=flags,
        summary=str(data.get("summary", "")).strip() or "Catalog reviewed.",
        reviewed_count=len(products),
        generated_at=now_ms(),
    )
    await _cache(merchant_id, review)
    return review


async def _cache(merchant_id: str, review: CatalogReview) -> None:
    try:
        redis = await get_redis()
        await redis.set(
            Keys.catalog_review(merchant_id),
            review.model_dump_json(),
            ex=TTL.CATALOG_REVIEW,
        )
    except Exception as e:
        logger.warning(f"[catalog] review cache failed for {merchant_id}: {e}")

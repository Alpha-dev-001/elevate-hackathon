"""Sprint 3 — LayoutDSL save / regenerate + StoreBirth SSE.

The merchant edits a draft DSL in the Store Builder and publishes it here. We
re-run normalize_dsl on every save so a hand-edited DSL still obeys the
structural guarantees (Defense Layer B). StoreBirth streams the Qwen pipeline.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_merchant
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import LayoutDSL, BrandToken
from app.services.layout_dsl import normalize_dsl, generate_layout_dsl, fallback_dsl_from_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/brand", tags=["brand"])


async def _load_token(merchant_id: str, db: AsyncSession) -> tuple[BrandProfileDB, BrandToken]:
    profile = await db.get(BrandProfileDB, merchant_id)
    if profile is None or not profile.brand_tokens:
        raise HTTPException(status_code=409, detail="Generate your brand before editing its layout")
    try:
        token = BrandToken.model_validate(profile.brand_tokens)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Corrupt brand token: {e}") from e
    return profile, token


async def _persist_dsl(profile: BrandProfileDB, token: BrandToken, dsl: LayoutDSL, merchant_id: str, db: AsyncSession) -> None:
    token.layout_dsl = dsl
    profile.brand_tokens = token.model_dump()  # reassign so SQLAlchemy flags JSON dirty
    await db.commit()
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        await r.set(f"layout_dsl:{merchant_id}", dsl.model_dump_json())
    except Exception as ce:  # cache is best-effort
        logger.warning("[brand] layout_dsl cache failed for %s: %s", merchant_id, ce)


@router.put("/dsl/{slug}")
async def save_dsl(
    slug: str,
    dsl: LayoutDSL,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Save the merchant's edited DSL. Re-normalized before persistence."""
    if merchant.slug != slug:
        raise HTTPException(status_code=403, detail="Not your store")
    profile, token = await _load_token(merchant.id, db)
    normalized = normalize_dsl(dsl.model_dump())
    await _persist_dsl(profile, token, normalized, merchant.id, db)
    return normalized.model_dump()


@router.post("/dsl/{slug}")
async def regenerate_dsl(
    slug: str,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Re-ask qwen-max to compose the store layout from scratch."""
    if merchant.slug != slug:
        raise HTTPException(status_code=403, detail="Not your store")
    profile, token = await _load_token(merchant.id, db)
    from sqlalchemy import select, func
    from app.models.db_models import ProductDB
    count = await db.scalar(select(func.count()).where(ProductDB.merchant_id == merchant.id)) or 0
    dsl = await generate_layout_dsl(token, merchant.store_name, merchant.category, count)
    await _persist_dsl(profile, token, dsl, merchant.id, db)
    return dsl.model_dump()

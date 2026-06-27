"""
Dev-only endpoints — regenerate brand data for existing stores.
Only registered in development. Never reachable in production.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import BrandToken
from app.services.brand import generate_brand_token, analyze_logo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/regenerate-brand/{slug}")
async def regenerate_brand(slug: str, db: AsyncSession = Depends(get_db)):
    """Re-generate BrandToken for an existing store using its current logo URL.
    Use this to upgrade existing Haree / Crest stores to the BrandToken schema.
    """
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")
    if not merchant.logo_url:
        raise HTTPException(status_code=422, detail="Store has no logo URL")

    brand_profile = await db.get(BrandProfileDB, merchant.id)
    if not brand_profile:
        raise HTTPException(status_code=422, detail="Store has no brand profile yet")

    logger.info(f"[dev] Regenerating BrandToken for {slug}")

    analysis = await analyze_logo(merchant.logo_url)
    brand_token = await generate_brand_token(analysis, merchant.store_name, merchant.category or "other")

    brand_profile.brand_tokens = brand_token.model_dump()
    await db.commit()

    logger.info(f"[dev] BrandToken saved for {slug}: layout.style={brand_token.layout.style}")
    return {
        "ok": True,
        "slug": slug,
        "layout_style": brand_token.layout.style,
        "brand_token": brand_token.model_dump(),
    }

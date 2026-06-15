"""
Public storefront data — no auth. Serves the customer-facing view of a live
store by slug: brand (palette, type, icons, tagline), products, promos, layout.

Reads SystemState from Redis (the hot-reload source) and the brand from
Redis/Postgres. Deliberately strips cost_price and exact stock — customers see
price and availability only.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis, Keys
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import (
    BrandPackage,
    GeneratedBrand,
    BrandGuardRules,
    LogoAnalysis,
    LayoutConfig,
    PublicProduct,
    PublicStore,
)
from app.services import delta as delta_svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/store", tags=["storefront"])


async def _load_brand(merchant_id: str, db: AsyncSession) -> BrandPackage | None:
    """Redis-first, Postgres fallback — same shape the onboarding flow stored."""
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.brand(merchant_id))
        if raw:
            return BrandPackage.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"[store] Redis brand read failed for {merchant_id}: {e}")

    row = await db.get(BrandProfileDB, merchant_id)
    if row is None:
        return None
    try:
        return BrandPackage(
            analysis=LogoAnalysis(**row.logo_analysis),
            brand=GeneratedBrand(**row.generated_brand["brand"]),
            guards=BrandGuardRules(**row.generated_brand["guards"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"[store] corrupt brand row for {merchant_id}: {e}")
        return None


@router.get("/{slug}", response_model=PublicStore)
async def get_public_store(slug: str, db: AsyncSession = Depends(get_db)):
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if merchant is None or not merchant.is_live:
        raise HTTPException(status_code=404, detail="Store not found")

    pkg = await _load_brand(merchant.id, db)
    if pkg is None:
        # Live but no brand on file — shouldn't happen, but don't 500 a customer.
        raise HTTPException(status_code=404, detail="Store not found")

    state = await delta_svc.load_state(merchant.id)
    products: list[PublicProduct] = []
    promos = []
    layout = LayoutConfig(
        color_accent=pkg.brand.palette.accent,
        layout_variant=pkg.brand.layout_variant,
        banner_text=pkg.brand.tagline,
    )
    if state is not None:
        layout = state.layout_config
        promos = list(state.active_promos.values())
        for p in state.products.values():
            if not p.qwen_generated and p.description is None and p.price <= 0:
                continue  # skip anything malformed
            products.append(
                PublicProduct(
                    id=p.id,
                    name=p.name,
                    price=p.price,
                    description=p.description,
                    image_url=p.image_url,
                    category=p.category,
                    available=p.stock > 0,
                )
            )

    return PublicStore(
        store_name=merchant.store_name,
        slug=merchant.slug,
        tagline=pkg.brand.tagline,
        palette=pkg.brand.palette,
        typography=pkg.brand.typography,
        icons=pkg.brand.icons,
        layout=layout,
        products=products,
        promos=promos,
    )

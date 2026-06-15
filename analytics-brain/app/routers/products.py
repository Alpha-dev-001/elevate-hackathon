"""
Product management — single add + CSV batch, each feeding ONE batched qwen-max
description call (never a per-product loop). Products persist to Postgres; if
the store is already live, the change is reflected into SystemState and pushed
to the storefront over the socket.
"""
from __future__ import annotations

import json
import time
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_merchant
from app.core.redis import get_redis, Keys
from app.core.ws_manager import manager
from app.models.db_models import MerchantDB, ProductDB, BrandProfileDB
from app.models.schemas import (
    Product,
    ProductCreate,
    ProductCSVRow,
    ProductBatchCreate,
    OnboardingStatus,
    WSMessage,
    WSEventType,
)
from app.services import brand as brand_svc
from app.services.brand import BrandGenerationError
from app.services import delta as delta_svc
from app.services.products import db_to_product, products_state_map, DEFAULT_COST_RATIO

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])

_NEUTRAL_VOICE = (
    "Clear, warm, and concise. Describe the product honestly and make it easy "
    "to picture in everyday use."
)


def _now() -> int:
    return int(time.time() * 1000)


async def _brand_voice(merchant_id: str, db: AsyncSession) -> str:
    """Brand voice for description generation — Redis first, Postgres fallback,
    neutral default if the merchant somehow has no brand yet."""
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.brand(merchant_id))
        if raw:
            voice = json.loads(raw).get("brand", {}).get("brand_voice_profile")
            if voice:
                return voice
    except Exception as e:
        logger.warning(f"[products] brand voice Redis read failed: {e}")

    row = await db.get(BrandProfileDB, merchant_id)
    if row:
        voice = (row.generated_brand or {}).get("brand", {}).get("brand_voice_profile")
        if voice:
            return voice
    return _NEUTRAL_VOICE


async def _describe(rows: list[ProductCSVRow], voice: str) -> tuple[dict[str, str], set[str]]:
    """Chunked, parallel descriptions. Returns ({name: description},
    fallback_names) — fallback_names didn't get real Qwen copy. Never raises;
    a Qwen outage degrades a chunk to neutral copy rather than blocking adds."""
    try:
        return await brand_svc.generate_descriptions(rows, voice)
    except BrandGenerationError as e:
        logger.warning(f"[products] description generation failed, using fallback: {e}")
        return ({r.name: f"{r.name}." for r in rows}, {r.name for r in rows})


async def _sync_state_if_live(db: AsyncSession, merchant_id: str) -> None:
    """If the store is published, refresh SystemState.products and push the
    update to the storefront. Best-effort — products already live in Postgres,
    so a Redis blip can't lose them."""
    try:
        state = await delta_svc.load_state(merchant_id)
        if state is None:
            return  # not live yet; publish seeds products from Postgres
        state.products = await products_state_map(db, merchant_id)
        state.version += 1
        state.last_updated = _now()
        await delta_svc.save_state(merchant_id, state)
        await manager.push_to_all(
            merchant_id,
            WSMessage(
                event=WSEventType.STATE_UPDATED,
                payload={"state": json.loads(state.model_dump_json())},
                merchant_id=merchant_id,
                timestamp=_now(),
            ),
        )
    except Exception as e:
        logger.warning(f"[products] could not sync live state for {merchant_id}: {e}")


async def _advance_to_products(merchant: MerchantDB) -> None:
    if merchant.onboarding_status == OnboardingStatus.BRAND_REVIEW.value:
        merchant.onboarding_status = OnboardingStatus.PRODUCTS.value


@router.post("", response_model=Product, status_code=201)
async def add_product(
    payload: ProductCreate,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    voice = await _brand_voice(merchant.id, db)
    row_in = ProductCSVRow(
        name=payload.name,
        price=payload.price,
        stock=payload.stock,
        image_url=payload.image_url or "",
        category=payload.category or "",
    )
    descs, fallbacks = await _describe([row_in], voice)

    product = ProductDB(
        id=f"prod_{uuid.uuid4().hex[:12]}",
        merchant_id=merchant.id,
        name=payload.name,
        description=descs.get(payload.name, f"{payload.name}."),
        price=payload.price,
        cost_price=payload.cost_price,
        stock=payload.stock,
        category=payload.category or "",
        image_urls=[payload.image_url] if payload.image_url else [],
        qwen_generated_description=payload.name not in fallbacks,
    )
    db.add(product)
    await _advance_to_products(merchant)
    await db.flush()

    await _sync_state_if_live(db, merchant.id)
    return db_to_product(product)


@router.post("/batch", response_model=list[Product], status_code=201)
async def add_products_batch(
    payload: ProductBatchCreate,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    rows = payload.products
    if not rows:
        raise HTTPException(status_code=400, detail="No product rows provided")
    if len(rows) > 200:
        raise HTTPException(status_code=400, detail="Batch capped at 200 products")

    voice = await _brand_voice(merchant.id, db)
    descs, fallbacks = await _describe(rows, voice)  # chunked, parallel

    created: list[ProductDB] = []
    for r in rows:
        product = ProductDB(
            id=f"prod_{uuid.uuid4().hex[:12]}",
            merchant_id=merchant.id,
            name=r.name,
            description=descs.get(r.name, f"{r.name}."),
            price=r.price,
            cost_price=round(r.price * DEFAULT_COST_RATIO, 2),  # CSV has no cost
            stock=r.stock,
            category=r.category or "",
            image_urls=[r.image_url] if r.image_url else [],
            qwen_generated_description=r.name not in fallbacks,
        )
        db.add(product)
        created.append(product)

    await _advance_to_products(merchant)
    await db.flush()

    await _sync_state_if_live(db, merchant.id)
    return [db_to_product(p) for p in created]


@router.get("", response_model=list[Product])
async def list_products(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    from app.services.products import load_products

    rows = await load_products(db, merchant.id)
    return [db_to_product(r) for r in rows]

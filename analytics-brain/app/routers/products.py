"""
Product management — single add + CSV batch, each feeding ONE batched qwen-max
description call (never a per-product loop). Products persist to Postgres; if
the store is already live, the change is reflected into SystemState and pushed
to the storefront over the socket.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_merchant
from app.core.redis import get_redis, Keys
from app.core.ws_manager import manager
from app.models.db_models import MerchantDB, ProductDB, BrandProfileDB
from app.models.schemas import (
    Product,
    ProductCreate,
    ProductUpdate,
    ProductCSVRow,
    ProductBatchCreate,
    VisionBatchRequest,
    VisionBatchProduct,
    VisionBatchResponse,
    OnboardingStatus,
    WSMessage,
    WSEventType,
)
from app.services import brand as brand_svc
from app.services.brand import BrandGenerationError
from app.services import delta as delta_svc
from app.services import interceptor
from app.services import vision as vision_svc
from app.services.products import db_to_product, products_state_map, DEFAULT_COST_RATIO
from app.services.profile import load_constraints

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


async def _owned_product(db: AsyncSession, merchant_id: str, product_id: str) -> ProductDB:
    p = await db.get(ProductDB, product_id)
    if p is None or p.merchant_id != merchant_id:
        raise HTTPException(status_code=404, detail="Product not found")
    return p


@router.patch("/{product_id}")
async def update_product(
    product_id: str,
    payload: ProductUpdate,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Partial edit. A price change runs through the interceptor: below cost is
    blocked (409), below the margin floor is clamped with a warning the merchant
    sees in `violations`. Stock/category/name/image/active update directly."""
    product = await _owned_product(db, merchant.id, product_id)
    data = payload.model_dump(exclude_unset=True)
    violations: list = []

    # Cost first — it's the basis for the margin check on any new price.
    if "cost_price" in data and data["cost_price"] is not None:
        product.cost_price = data["cost_price"]

    if "price" in data and data["price"] is not None:
        constraints = await load_constraints(db, merchant.id)
        final, vs = interceptor.enforce_price(
            cost_price=product.cost_price,
            proposed_price=float(data["price"]),
            constraints=constraints,
            product_id=product.id,
        )
        violations = [v.model_dump() for v in vs]
        if interceptor.blocked(vs):
            msg = next((v.message for v in vs if v.severity == "blocked"), "Price blocked.")
            raise HTTPException(status_code=409, detail=msg)
        product.price = final

    if "name" in data and data["name"] is not None:
        product.name = data["name"]
    if "stock" in data and data["stock"] is not None:
        product.stock = data["stock"]
    if "category" in data and data["category"] is not None:
        product.category = data["category"]
    if "image_url" in data and data["image_url"] is not None:
        product.image_urls = [data["image_url"]] if data["image_url"] else []
    if "is_active" in data and data["is_active"] is not None:
        product.is_active = data["is_active"]

    await db.flush()
    await _sync_state_if_live(db, merchant.id)
    return {"product": db_to_product(product).model_dump(), "violations": violations}


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete — keeps order history intact, removes the product from the
    live store."""
    product = await _owned_product(db, merchant.id, product_id)
    product.is_active = False
    await db.flush()
    await _sync_state_if_live(db, merchant.id)


# ── Vision batch (photo drop) ────────────────────────────────────────────────

VISION_CONCURRENCY = 5
DEFAULT_BASELINE_PRICE = 50.0


async def _baseline_price(db: AsyncSession, merchant_id: str) -> float:
    """Baseline price for vision anchoring. Median of existing products, or a
    sensible default if the catalog is empty. Median handles outliers better
    than mean (one $500 product in a $20 catalog doesn't skew the anchor)."""
    from app.services.products import load_products
    rows = await load_products(db, merchant_id)
    if rows:
        prices = [r.price for r in rows if r.price > 0]
        if prices:
            return statistics.median(prices)
    return DEFAULT_BASELINE_PRICE


@router.post("/vision-batch", response_model=VisionBatchResponse, status_code=201)
async def vision_batch(
    payload: VisionBatchRequest,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Drop a batch of product photos — each gets one qwen-vl-max pass that
    identifies the product, drafts a description in the brand voice, and
    suggests a price. ``confident=False`` items are still created but flagged
    for the CatalogReview human-in-the-loop step. Vision descriptions are
    used directly — no second qwen-max call."""
    urls = payload.image_urls
    if not urls:
        raise HTTPException(status_code=400, detail="No image URLs provided")
    if len(urls) > 50:
        raise HTTPException(status_code=400, detail="Vision batch capped at 50 images")

    voice = await _brand_voice(merchant.id, db)
    baseline = await _baseline_price(db, merchant.id)
    store_name = merchant.store_name

    sem = asyncio.Semaphore(VISION_CONCURRENCY)

    async def analyze_one(url: str):
        async with sem:
            try:
                result = await vision_svc.analyze_product_image(
                    image_ref=url,
                    store_name=store_name,
                    brand_voice=voice,
                    baseline_price=baseline,
                )
                return url, result
            except Exception as e:
                logger.warning(f"[vision-batch] failed for {url}: {e}")
                return url, None

    results = await asyncio.gather(*[analyze_one(u) for u in urls])

    created: list[VisionBatchProduct] = []
    failed_urls: list[str] = []

    for url, vision_result in results:
        if vision_result is None:
            failed_urls.append(url)
            continue

        product = ProductDB(
            id=f"prod_{uuid.uuid4().hex[:12]}",
            merchant_id=merchant.id,
            name=vision_result.name,
            description=vision_result.description or f"{vision_result.name}.",
            price=vision_result.suggested_price,
            cost_price=round(vision_result.suggested_price * DEFAULT_COST_RATIO, 2),
            stock=10,
            category=vision_result.category or "",
            image_urls=[url],
            is_active=False,  # pending — merchant approves before going live
            qwen_generated_description=True,
        )
        db.add(product)
        created.append(VisionBatchProduct(
            product=db_to_product(product),
            confident=vision_result.confident,
        ))

    await _advance_to_products(merchant)
    await db.flush()
    await _sync_state_if_live(db, merchant.id)

    return VisionBatchResponse(products=created, failed_urls=failed_urls)


@router.get("/pending", response_model=list[Product])
async def list_pending_products(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Vision-created products awaiting merchant approval (is_active=False)."""
    rows = await db.scalars(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant.id, ProductDB.is_active.is_(False))
        .order_by(ProductDB.created_at.desc())
    )
    return [db_to_product(r) for r in rows]


@router.post("/{product_id}/approve", response_model=Product)
async def approve_product(
    product_id: str,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending vision-product — flips it live and syncs the
    storefront immediately so the merchant sees it appear without a full
    republish."""
    product = await _owned_product(db, merchant.id, product_id)
    product.is_active = True
    await db.flush()
    await _sync_state_if_live(db, merchant.id)
    return db_to_product(product)


@router.post("/approve-all", response_model=list[Product])
async def approve_all_products(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Approve every pending vision-product in one shot. Syncs the live
    storefront once at the end."""
    rows = await db.scalars(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant.id, ProductDB.is_active.is_(False))
    )
    approved = []
    for row in rows:
        row.is_active = True
        approved.append(row)
    await db.flush()
    if approved:
        await _sync_state_if_live(db, merchant.id)
    return [db_to_product(r) for r in approved]

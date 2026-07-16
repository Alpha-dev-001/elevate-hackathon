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

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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


async def _describe(rows: list[ProductCSVRow], voice: str, memory_ctx: str = "", merchant_id: str | None = None) -> tuple[dict[str, str], set[str]]:
    """Chunked, parallel descriptions. Returns ({name: description},
    fallback_names) — fallback_names didn't get real Qwen copy. Never raises;
    a Qwen outage degrades a chunk to neutral copy rather than blocking adds."""
    try:
        return await brand_svc.generate_descriptions(rows, voice, memory_ctx, merchant_id)
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


def _schedule_featuring_check(background: BackgroundTasks, merchant_id: str, new_product_ids: list[str]) -> None:
    """Fire the featuring trigger once per batch, never per product — same
    fire-and-forget pattern behavior.py uses for the reactive trigger. Uses
    a fresh DB session so it never races the request session's teardown."""
    async def _check():
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.core.database import get_engine
        from app.core.redis import get_redis
        from app.services.product_featuring import evaluate_new_products

        redis = await get_redis()
        async with AsyncSession(get_engine()) as session:
            await evaluate_new_products(merchant_id, new_product_ids, session, redis)

    background.add_task(_check)


def _schedule_image_mirror(background: BackgroundTasks, merchant_id: str, product_id: str, image_url: str) -> None:
    """Mirror a CSV/manual image_url to our own OSS in the background — never
    blocks the add-product response. Vision-batch products already have an
    OSS-hosted image_url by the time they reach this router, so this is a
    no-op for them (mirror_image detects "already ours" and returns None)."""
    async def _mirror():
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.core.database import get_engine
        from app.services.image_mirror import mirror_image

        new_url = await mirror_image(image_url, merchant_id)
        if not new_url:
            return
        async with AsyncSession(get_engine()) as session:
            product = await session.get(ProductDB, product_id)
            if product and product.merchant_id == merchant_id and product.image_urls and product.image_urls[0] == image_url:
                product.image_urls = [new_url] + product.image_urls[1:]
                await session.commit()
                await _sync_state_if_live(session, merchant_id)
                logger.info(f"[image_mirror] mirrored image for {product_id}")

    background.add_task(_mirror)


@router.post("", response_model=Product, status_code=201)
async def add_product(
    payload: ProductCreate,
    background: BackgroundTasks,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    voice = await _brand_voice(merchant.id, db)
    # Load merchant memory for description personalisation.
    from app.services.memory import get_memory, build_memory_context
    redis = await get_redis()
    mem_ctx = build_memory_context(await get_memory(merchant.id, db, redis))
    row_in = ProductCSVRow(
        name=payload.name,
        price=payload.price,
        stock=payload.stock,
        image_url=payload.image_url or "",
        category=payload.category or "",
    )
    descs, fallbacks = await _describe([row_in], voice, mem_ctx, merchant.id)

    product = ProductDB(
        id=f"prod_{uuid.uuid4().hex[:12]}",
        merchant_id=merchant.id,
        name=payload.name,
        description=descs.get(payload.name, f"{payload.name}."),
        price=payload.price,
        cost_price=payload.cost_price,
        baseline_price=payload.price,
        stock=payload.stock,
        category=payload.category or "",
        image_urls=[payload.image_url] if payload.image_url else [],
        qwen_generated_description=payload.name not in fallbacks,
    )
    db.add(product)
    await _advance_to_products(merchant)
    await db.flush()

    await _sync_state_if_live(db, merchant.id)
    _schedule_featuring_check(background, merchant.id, [product.id])
    if payload.image_url:
        _schedule_image_mirror(background, merchant.id, product.id, payload.image_url)
    return db_to_product(product)


@router.post("/batch", response_model=list[Product], status_code=201)
async def add_products_batch(
    payload: ProductBatchCreate,
    background: BackgroundTasks,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    rows = payload.products
    if not rows:
        raise HTTPException(status_code=400, detail="No product rows provided")
    if len(rows) > 200:
        raise HTTPException(status_code=400, detail="Batch capped at 200 products")

    voice = await _brand_voice(merchant.id, db)
    # Load merchant memory for description personalisation.
    from app.services.memory import get_memory, build_memory_context
    redis = await get_redis()
    mem_ctx = build_memory_context(await get_memory(merchant.id, db, redis))
    descs, fallbacks = await _describe(rows, voice, mem_ctx, merchant.id)  # chunked, parallel

    created: list[ProductDB] = []
    for r in rows:
        product = ProductDB(
            id=f"prod_{uuid.uuid4().hex[:12]}",
            merchant_id=merchant.id,
            name=r.name,
            description=descs.get(r.name, f"{r.name}."),
            price=r.price,
            cost_price=round(r.price * DEFAULT_COST_RATIO, 2),  # CSV has no cost
            baseline_price=r.price,
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
    _schedule_featuring_check(background, merchant.id, [p.id for p in created])
    for p, r in zip(created, rows):
        if r.image_url:
            _schedule_image_mirror(background, merchant.id, p.id, r.image_url)
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
    sees in `violations`. Stock/category/name/image/active update directly.

    Every edit is silently recorded in qwen_memory so future vision calls and
    decision cycles learn the merchant's preferences (pricing style, naming
    conventions, category choices)."""
    product = await _owned_product(db, merchant.id, product_id)
    data = payload.model_dump(exclude_unset=True)
    violations: list = []

    # Snapshot old values for the memory entry before mutating.
    _old: dict[str, str] = {}
    for key in ("name", "price", "cost_price", "category", "stock", "is_active"):
        if key in data and data[key] is not None:
            _old[key] = str(getattr(product, key, ""))

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

    # ── Memory hook: record what the merchant changed so Qwen learns ──
    if _old:
        changes = []
        for key, old_val in _old.items():
            new_val = str(getattr(product, key, ""))
            if old_val != new_val:
                changes.append(f"{key}: {old_val}→{new_val}")
        if changes:
            try:
                from app.services.memory import write_memory
                from app.models.schemas import MemoryEntry
                redis = await get_redis()
                entry = MemoryEntry(
                    action_type="merchant_edit",
                    trigger=f"edited '{product.name}'",
                    outcome="; ".join(changes),
                    merchant_behavior="edited",
                    notes=f"merchant manually adjusted product",
                )
                await write_memory(merchant.id, entry, db, redis)
            except Exception as e:  # noqa: BLE001 — memory write must never block the edit
                logger.warning("[products] memory write failed for edit on %s: %s", product_id, e)

    await _sync_state_if_live(db, merchant.id)
    return {"product": db_to_product(product).model_dump(), "violations": violations}


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Pending products (never approved, is_active=False) are hard-deleted —
    they were never live and no orders reference them.  Active products are
    soft-deleted (is_active=False) to keep order history intact."""
    product = await _owned_product(db, merchant.id, product_id)
    if not product.is_active:
        await db.delete(product)
    else:
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

    # Load merchant memory — Qwen learns from past edits silently.
    from app.services.memory import get_memory, build_memory_context
    redis = await get_redis()
    memories = await get_memory(merchant.id, db, redis)
    memory_ctx = build_memory_context(memories)

    sem = asyncio.Semaphore(VISION_CONCURRENCY)

    async def analyze_one(url: str):
        async with sem:
            # Cheap reachability/content-type check first — a confirmed-dead
            # or non-image URL never reaches Qwen, so it costs nothing.
            if not await vision_svc.is_probably_image(url):
                logger.info(f"[vision-batch] skipping dead/non-image URL: {url}")
                return url, None
            try:
                result = await vision_svc.analyze_product_image(
                    image_ref=url,
                    store_name=store_name,
                    brand_voice=voice,
                    baseline_price=baseline,
                    memory_context=memory_ctx,
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
            baseline_price=vision_result.suggested_price,
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


# ── Duplicate detection & catalog cleanup ──────────────────────────────────────

from app.services.duplicate_scan import duplicate_candidate_groups
from app.models.schemas import DeduplicateReport, DuplicateGroup


@router.post("/deduplicate", response_model=DeduplicateReport)
async def deduplicate_products(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Scan the merchant's catalog for duplicate products (same image_url
    AND same name — a shared stock/placeholder photo across genuinely
    different products is never treated as a duplicate).

    Qwen-generated duplicates are auto-resolved: the first product is kept,
    extras are hard-deleted (they were never live or are redundant vision
    duplicates). Merchant-written duplicates are flagged for review — the
    merchant decides whether they intended two separate listings."""
    rows = await db.scalars(
        select(ProductDB).where(ProductDB.merchant_id == merchant.id)
    )
    products = list(rows)
    total_scanned = len(products)

    auto_merged: list[DuplicateGroup] = []
    needs_review: list[DuplicateGroup] = []
    total_duplicates = 0

    for group in duplicate_candidate_groups(products):
        image_url = group[0].image_urls[0]
        total_duplicates += len(group) - 1
        all_qwen = all(p.qwen_generated_description for p in group)

        if all_qwen:
            # Qwen-generated: keep the first, hard-delete the rest.
            keeper = group[0]
            for dup in group[1:]:
                await db.delete(dup)
            auto_merged.append(DuplicateGroup(
                image_url=image_url,
                product_ids=[p.id for p in group],
                names=[p.name for p in group],
                qwen_generated=True,
                auto_resolved=True,
            ))
        else:
            # Merchant-written: flag for review — don't auto-delete.
            needs_review.append(DuplicateGroup(
                image_url=image_url,
                product_ids=[p.id for p in group],
                names=[p.name for p in group],
                qwen_generated=False,
                auto_resolved=False,
            ))

    await db.flush()
    if auto_merged:
        await _sync_state_if_live(db, merchant.id)

    return DeduplicateReport(
        auto_merged=auto_merged,
        needs_review=needs_review,
        total_scanned=total_scanned,
        total_duplicates=total_duplicates,
    )


# ── Qwen-powered catalog audit ───────────────────────────────────────────────

from pydantic import BaseModel as _BM

class CatalogFinding(_BM):
    """One issue Qwen found in the catalog."""
    product_id: str
    product_name: str
    issue_type: str       # pricing_anomaly | missing_category | naming_issue | duplicate | description_quality
    severity: str         # low | medium | high
    description: str
    suggested_fix: str    # human-readable suggestion

class CatalogAuditReport(_BM):
    findings: list[CatalogFinding]
    catalog_score: int    # 0-100 quality score
    summary: str          # Qwen's overall assessment


CATALOG_AUDIT_PROMPT = """You are an expert e-commerce catalog auditor.
Review this store's product catalog and identify quality issues.

Store: {store_name} ({category})

For each product, check:
1. **Pricing anomalies**: price seems unreasonable for the product type (e.g. $500 for basic slides, $2 for a designer bag)
2. **Missing categories**: product has no category or a vague one like "other"
3. **Naming issues**: name is generic ("Product 1"), has typos, or doesn't match typical e-commerce naming
4. **Description quality**: description is too short, generic, or doesn't describe the actual product
5. **Duplicates**: products that seem to be the same item listed separately

Return ONLY a JSON object:
{{
  "findings": [
    {{
      "product_id": "<id>",
      "product_name": "<name>",
      "issue_type": "pricing_anomaly|missing_category|naming_issue|duplicate|description_quality",
      "severity": "low|medium|high",
      "description": "<what's wrong>",
      "suggested_fix": "<specific, actionable fix>"
    }}
  ],
  "catalog_score": <0-100, where 100 is a perfect catalog>,
  "summary": "<1-2 sentence overall assessment>"
}}

If the catalog is clean, return an empty findings array with a high score.
Be honest but constructive. Only flag real issues, not stylistic preferences.

Products:
{products_json}"""


@router.post("/catalog-audit", response_model=CatalogAuditReport)
async def catalog_audit(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Qwen-max reviews the entire catalog for quality issues. Returns a
    structured report with findings and a catalog quality score. This is
    advisory — the merchant decides which findings to act on.

    Token-efficient: one qwen-max call for the entire catalog (up to 100
    products), not per-product."""
    from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError
    from app.core.config import get_settings

    rows = await db.scalars(
        select(ProductDB).where(ProductDB.merchant_id == merchant.id).limit(100)
    )
    products = list(rows)
    if not products:
        return CatalogAuditReport(findings=[], catalog_score=100, summary="Empty catalog — no products to audit.")

    products_json = json.dumps([
        {
            "id": p.id, "name": p.name, "price": p.price,
            "category": p.category or "(none)",
            "description": (p.description or "")[:200],
        }
        for p in products
    ], ensure_ascii=False)

    prompt = CATALOG_AUDIT_PROMPT.format(
        store_name=merchant.store_name,
        category=merchant.category,
        products_json=products_json,
    )

    try:
        raw = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000, temperature=0.3, timeout=60.0,
        )
        data = _extract_json(raw)
        findings = []
        for f in (data.get("findings") or []):
            try:
                findings.append(CatalogFinding(**f))
            except Exception:
                continue
        return CatalogAuditReport(
            findings=findings,
            catalog_score=max(0, min(100, int(data.get("catalog_score", 50)))),
            summary=str(data.get("summary", "Audit complete.")),
        )
    except Exception as e:
        logger.warning("[catalog-audit] Qwen call failed: %s", e)
        return CatalogAuditReport(
            findings=[], catalog_score=50,
            summary="Qwen was unavailable for the audit. Run the deduplication scan instead.",
        )


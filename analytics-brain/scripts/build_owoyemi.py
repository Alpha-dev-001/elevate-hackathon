"""
Build the "Owoyemi of Offa" demo store from a logo + a folder of product photos.

Pipeline (reuses the real onboarding services — nothing faked):
  1. Upload logo + every product photo to OSS (public-read).
  2. qwen-vl-max → qwen-max: brand package + BrandToken + LayoutDSL from the logo.
  3. qwen-vl-max per product photo → name / brand / description / category /
     colourways / a price anchored to the merchant BASELINE (never web-MSRP).
     Low-confidence reads are created inactive and reported — honest, not silent.
  4. Publish: SystemState in Redis, merchant live at /s/owoyemi-of-offa.

Idempotent: wipes this merchant's products and rebuilds each run.

Run:
  docker compose exec -e LIMIT=6 api python scripts/build_owoyemi.py   # validate
  docker compose exec api python scripts/build_owoyemi.py              # full 98
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

import oss2
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.database import get_session_factory
from app.core.security import hash_password
from app.models.db_models import MerchantDB, BrandProfileDB, ProductDB
from app.models.schemas import (
    BrandToken, SystemState, LayoutConfig, BusinessProfile, BusinessConstraints,
    OnboardingStatus,
)
from app.services import brand as brand_svc
from app.services.products import DEFAULT_COST_RATIO
from app.services.vision import analyze_product_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("build_owoyemi")

# ── Config ───────────────────────────────────────────────────────────────────
STORE_NAME = "Owoyemi of Offa"
SLUG = "owoyemi-of-offa"
CATEGORY = "fashion"
DESCRIPTION = "Curated designer footwear and accessories."
EMAIL = os.getenv("DEMO_MERCHANT_EMAIL", "owoyemi@demo.elevate")
# Never hard-code a working credential in a public repo. Set DEMO_MERCHANT_PASSWORD
# when (re)building the demo store; the fallback is a placeholder, not a real login.
PASSWORD = os.getenv("DEMO_MERCHANT_PASSWORD", "change-me-before-use")
BASELINE_PRICE = float(os.getenv("BASELINE_PRICE", "25"))
DEFAULT_STOCK = 25
VL_CONCURRENCY = int(os.getenv("VL_CONCURRENCY", "4"))
LIMIT = int(os.getenv("LIMIT", "0"))  # 0 = all

ASSETS = Path(__file__).parent / "assets" / "owoyemi"
LOGO_PATH = ASSETS / "logo.jpg"
PRODUCTS_DIR = ASSETS / "products"

_now = lambda: int(time.time() * 1000)


def _bucket():
    s = get_settings()
    if not (s.oss_access_key_id and s.oss_access_key_secret and s.oss_bucket and s.oss_region):
        raise RuntimeError("OSS not configured (check analytics-brain/.env)")
    endpoint = f"https://oss-{s.oss_region}.aliyuncs.com"
    auth = oss2.AuthV4(s.oss_access_key_id, s.oss_access_key_secret)
    return oss2.Bucket(auth, endpoint, s.oss_bucket, region=s.oss_region), s


def oss_put(bucket, s, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
    """Upload bytes to OSS public-read; return the public URL."""
    bucket.put_object(
        key, data,
        headers={"x-oss-object-acl": "public-read", "Content-Type": content_type},
    )
    return f"https://{s.oss_bucket}.oss-{s.oss_region}.aliyuncs.com/{key}"


async def upsert_merchant(db) -> MerchantDB:
    m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == SLUG))
    if m is None:
        m = MerchantDB(
            id=f"merchant_{uuid.uuid4().hex[:12]}",
            email=EMAIL,
            hashed_password=hash_password(PASSWORD),
            store_name=STORE_NAME,
            slug=SLUG,
            category=CATEGORY,
            description=DESCRIPTION,
            onboarding_status=OnboardingStatus.LOGO_UPLOAD.value,
        )
        db.add(m)
        await db.flush()
        logger.info("created merchant %s (%s)", m.id, SLUG)
    else:
        logger.info("reusing merchant %s (%s)", m.id, SLUG)
    # wipe products so re-runs don't duplicate
    await db.execute(delete(ProductDB).where(ProductDB.merchant_id == m.id))
    return m


async def build_brand(db, m: MerchantDB, bucket, s) -> brand_svc.BrandPackage:
    logo_url = oss_put(bucket, s, f"logos/{m.id}/logo_{int(time.time())}.jpg", LOGO_PATH.read_bytes())
    m.logo_url = logo_url
    logger.info("logo → %s", logo_url)

    pkg = await brand_svc.build_brand_package(logo_url, STORE_NAME, CATEGORY, DESCRIPTION)
    row = await db.get(BrandProfileDB, m.id)
    generated = {"brand": pkg.brand.model_dump(), "guards": pkg.guards.model_dump()}
    if row is None:
        row = BrandProfileDB(merchant_id=m.id, logo_analysis=pkg.analysis.model_dump(), generated_brand=generated)
        db.add(row)
    else:
        row.logo_analysis = pkg.analysis.model_dump()
        row.generated_brand = generated

    # BrandToken + LayoutDSL so the storefront renders the composed (not fallback) layout
    token = await brand_svc.generate_brand_token(pkg.analysis, STORE_NAME, CATEGORY)
    from app.services.layout_dsl import generate_layout_dsl
    token.layout_dsl = await generate_layout_dsl(token, STORE_NAME, CATEGORY, product_count=1)
    row.brand_tokens = token.model_dump()
    await db.flush()
    logger.info("brand built: style=%s voice=%.40s", token.layout.style, pkg.brand.brand_voice_profile)
    return pkg


async def catalog_products(db, m: MerchantDB, bucket, s, brand_voice: str):
    paths = sorted(PRODUCTS_DIR.glob("*.jpg"))
    if LIMIT:
        paths = paths[:LIMIT]
    logger.info("cataloguing %d product photos (concurrency=%d, baseline=$%.0f)",
                len(paths), VL_CONCURRENCY, BASELINE_PRICE)

    sem = asyncio.Semaphore(VL_CONCURRENCY)
    unsure: list[str] = []
    made = 0

    async def one(idx: int, path: Path):
        nonlocal made
        async with sem:
            try:
                url = oss_put(bucket, s, f"products/{m.id}/{path.stem}_{uuid.uuid4().hex[:6]}.jpg", path.read_bytes())
            except Exception as e:
                logger.warning("  [%d] OSS upload failed for %s: %s", idx, path.name, e)
                return None
            try:
                pv = await analyze_product_image(
                    image_ref=url, store_name=STORE_NAME,
                    brand_voice=brand_voice, baseline_price=BASELINE_PRICE,
                )
            except Exception as e:
                logger.warning("  [%d] VL failed for %s: %s", idx, path.name, e)
                return None
            return url, pv

    results = await asyncio.gather(*(one(i, p) for i, p in enumerate(paths)))

    for res in results:
        if not res:
            continue
        url, pv = res
        name = pv.name
        if pv.colors:
            name = f"{pv.name} ({'/'.join(pv.colors)})" if pv.confident else pv.name
        product = ProductDB(
            id=f"prod_{uuid.uuid4().hex[:12]}",
            merchant_id=m.id,
            name=name,
            description=pv.description or f"{pv.name}.",
            price=pv.suggested_price,
            baseline_price=pv.suggested_price,
            cost_price=round(pv.suggested_price * DEFAULT_COST_RATIO, 2),
            stock=DEFAULT_STOCK,
            category=pv.category or "footwear",
            image_urls=[url],
            is_active=pv.confident,          # unsure → hidden draft, honest
            qwen_generated_description=True,
        )
        db.add(product)
        made += 1
        if not pv.confident:
            unsure.append(pv.name)

    await db.flush()
    logger.info("catalogued %d products (%d active, %d flagged for review)",
                made, made - len(unsure), len(unsure))
    if unsure:
        logger.info("NEEDS REVIEW (Qwen wasn't confident): %s", unsure)
    return made


async def publish(db, m: MerchantDB, pkg):
    from app.services.products import products_state_map
    from app.services import delta as delta_svc
    from app.core.redis import get_redis, Keys

    state = SystemState(
        version=1, last_updated=_now(),
        products=await products_state_map(db, m.id),
        active_promos={},
        layout_config=LayoutConfig(
            banner_text=pkg.brand.tagline,
            color_accent=pkg.brand.palette.accent,
            layout_variant=pkg.brand.layout_variant,
        ),
        qr_campaigns={},
    )
    await delta_svc.save_state(m.id, state)
    profile = BusinessProfile(
        merchant_id=m.id, store_name=STORE_NAME,
        constraints=BusinessConstraints(), products=[],
    )
    r = await get_redis()
    await r.set(Keys.profile(m.id), profile.model_dump_json())
    m.is_live = True
    m.onboarding_status = OnboardingStatus.LIVE.value
    logger.info("published %d products", len(state.products))


async def main():
    if not LOGO_PATH.exists():
        raise SystemExit(f"logo missing at {LOGO_PATH}")
    bucket, s = _bucket()
    factory = get_session_factory()
    async with factory() as db:
        m = await upsert_merchant(db)
        pkg = await build_brand(db, m, bucket, s)
        await catalog_products(db, m, bucket, s, pkg.brand.brand_voice_profile)
        await publish(db, m, pkg)
        await db.commit()
    print("\n✅ DONE")
    print(f"   Store:    {get_settings().frontend_url}/s/{SLUG}")
    print(f"   Terminal login: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())

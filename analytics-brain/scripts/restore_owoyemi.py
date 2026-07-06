"""Restore owoyemi-of-offa after a stray re-onboarding (a burger logo) regenerated
and contaminated its brand / logo / layout. KEEPS the 98 catalogued products —
only the brand identity was corrupted, not the catalog.

Steps (fast, ~a few Qwen calls — does NOT re-catalogue products):
  1. Re-derive the brand from the REAL peacock logo (re-uploads it, sets logo_url).
  2. Lock the intended hero-led layout DSL (the burger regen changed the sections).
  3. Lock the accent to #C0C0C0 (Qwen's original silver choice) in token + palette.
  4. Flip status back to live; refresh the Redis brand + dsl caches; clear phase.

Run: docker compose exec api sh -c "cd /app && python -m scripts.restore_owoyemi"
"""
import asyncio

from sqlalchemy import select

from app.core.database import get_session_factory
from app.core.redis import get_redis, Keys
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import (
    BrandToken, OnboardingStatus, BrandPackage, LogoAnalysis, GeneratedBrand, BrandGuardRules,
)
from app.services.layout_dsl import normalize_dsl
from scripts.build_owoyemi import _bucket, build_brand, SLUG

# The intended owoyemi layout (same as restore_owoyemi_dsl) + original accent.
GOOD_SECTIONS = [
    {"type": "hero", "variant": "split-50-50", "props": {}},
    {"type": "banner", "variant": "static-strip", "props": {}},
    {"type": "product_grid", "variant": "single-spotlight", "props": {}},
    {"type": "story", "variant": "quote-callout", "props": {}},
]
ACCENT = "#C0C0C0"


async def main():
    bucket, s = _bucket()
    factory = get_session_factory()
    async with factory() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == SLUG))
        if m is None:
            raise SystemExit("owoyemi merchant not found")

        # 1. re-derive brand from the real logo (re-uploads logo, regen brand+token+dsl)
        await build_brand(db, m, bucket, s)

        profile = await db.get(BrandProfileDB, m.id)
        token = BrandToken.model_validate(profile.brand_tokens)

        # 2. lock the intended layout DSL
        cur = token.layout_dsl.model_dump(mode="json") if token.layout_dsl else {}
        dsl = normalize_dsl({
            "sections": GOOD_SECTIONS,
            "global_config": cur.get("global_config", {}),
            "custom_css": cur.get("custom_css", ""),
        })
        token.layout_dsl = dsl

        # 3. lock accent in the token AND the legacy palette (PublicStore.palette)
        token.colors = token.colors.model_copy(update={"accent": ACCENT})
        profile.brand_tokens = token.model_dump()
        gen = dict(profile.generated_brand or {})
        brand = dict(gen.get("brand") or {})
        pal = dict(brand.get("palette") or {})
        pal["accent"] = ACCENT
        brand["palette"] = pal
        gen["brand"] = brand
        profile.generated_brand = gen

        # 4. status live
        m.is_live = True
        m.onboarding_status = OnboardingStatus.LIVE.value
        await db.commit()

        # refresh Redis caches so the storefront serves the restored brand at once
        pkg = BrandPackage(
            analysis=LogoAnalysis(**profile.logo_analysis),
            brand=GeneratedBrand(**gen["brand"]),
            guards=BrandGuardRules(**gen["guards"]),
        )
        r = await get_redis()
        await r.set(Keys.brand(m.id), pkg.model_dump_json())
        await r.set(f"layout_dsl:{m.id}", dsl.model_dump_json())
        await r.delete(Keys.onboarding(m.id))

        print("RESTORED owoyemi:")
        print("  logo_url  :", (m.logo_url or "")[-40:])
        print("  brand     :", brand.get("store_name"), "| palette:", brand.get("palette"))
        print("  sections  :", [(x["type"], x["variant"]) for x in dsl.model_dump(mode="json")["sections"]])
        print("  status    :", m.onboarding_status, "| is_live:", m.is_live)


if __name__ == "__main__":
    asyncio.run(main())

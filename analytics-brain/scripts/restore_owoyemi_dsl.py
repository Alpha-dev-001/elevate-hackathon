"""Restore owoyemi-of-offa's layout DSL after the builder-publish enum bug nuked it
to a generic grid+story. Sets the intended hero-led layout, re-normalizes, and
refreshes the Redis cache.

Run: docker compose exec api sh -c "cd /app && python -m scripts.restore_owoyemi_dsl"
"""
import asyncio
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import BrandToken
from app.services.layout_dsl import normalize_dsl

GOOD_SECTIONS = [
    {"type": "hero", "variant": "split-50-50", "props": {}},
    {"type": "banner", "variant": "static-strip", "props": {}},
    {"type": "product_grid", "variant": "single-spotlight", "props": {}},
    {"type": "story", "variant": "quote-callout", "props": {}},
]


async def main():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == "owoyemi-of-offa"))
        profile = await db.get(BrandProfileDB, m.id)
        token = BrandToken.model_validate(profile.brand_tokens)
        current = token.layout_dsl.model_dump(mode="json") if token.layout_dsl else {}
        dsl = normalize_dsl({
            "sections": GOOD_SECTIONS,
            "global_config": current.get("global_config", {}),
            "custom_css": current.get("custom_css", ""),
        })
        token.layout_dsl = dsl
        profile.brand_tokens = token.model_dump()
        await db.commit()
        try:
            from app.core.redis import get_redis
            r = await get_redis()
            await r.set(f"layout_dsl:{m.id}", dsl.model_dump_json())
        except Exception as e:
            print("redis cache skip:", e)
        print("restored sections:", [(s.type.value, s.variant) for s in dsl.sections])


if __name__ == "__main__":
    asyncio.run(main())

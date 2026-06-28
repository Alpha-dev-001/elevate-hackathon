"""Backfill the new per-store page-variant DSL fields (add_to_cart,
product_detail, cart_style) onto an existing store by regenerating its DSL from
its brand token via the deterministic composer. Use for stores whose DSL
predates these fields (e.g. haree). Crest uses diversify_crest.py instead
(it has explicit overrides).

Run:  docker compose exec api sh -c 'cd /app && PYTHONPATH=/app python scripts/backfill_page_variants.py haree'
"""
import asyncio
import sys

from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import BrandToken
from app.services.layout_dsl import fallback_dsl_from_token


async def main(slug: str):
    factory = get_session_factory()
    async with factory() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
        if not m:
            print(f"no merchant '{slug}'"); return
        profile = await db.get(BrandProfileDB, m.id)
        if not profile or not profile.brand_tokens:
            print(f"{slug} has no brand_tokens"); return

        token = BrandToken.model_validate(profile.brand_tokens)
        dsl = fallback_dsl_from_token(token)   # now includes add_to_cart/product_detail/cart_style
        token.layout_dsl = dsl
        profile.brand_tokens = token.model_dump()
        await db.commit()
        try:
            from app.core.redis import get_redis
            r = await get_redis()
            await r.set(f"layout_dsl:{m.id}", dsl.model_dump_json())
        except Exception as e:
            print("redis skip:", e)
        gc = dsl.global_config
        print(f"{slug} page-variants → add_to_cart={gc.add_to_cart} "
              f"product_detail={gc.product_detail} cart_style={gc.cart_style} "
              f"nav={gc.nav_style} card={gc.product_card}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "haree"))

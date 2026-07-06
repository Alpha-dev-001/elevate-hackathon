"""Owoyemi's stored palette accent came back #FFFFFF (white) — a bug: Qwen's OWN
brand guard reasoned about #C0C0C0 (silver, "subtle elegance"). Align the stored
accent to Qwen's actual choice so palette, guard, and store all agree. (Root
brand-gen mismatch — palette.accent != guard color — is a logged follow-up.)
The storefront's readableOn/--s-cta layer keeps silver CTAs legible; the silver
identity stays for subtle accents, as Qwen intended.

Run: docker compose exec api sh -c "cd /app && python -m scripts.fix_owoyemi_accent"
"""
import asyncio
from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import BrandToken

ACCENT = "#C0C0C0"  # Qwen's actual choice, per its brand guard — not an imposed color


async def main():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == "owoyemi-of-offa"))
        profile = await db.get(BrandProfileDB, m.id)

        token = BrandToken.model_validate(profile.brand_tokens)
        token.colors = token.colors.model_copy(update={"accent": ACCENT})
        profile.brand_tokens = token.model_dump()

        # keep the legacy palette in sync (PublicStore.palette)
        gen = dict(profile.generated_brand or {})
        brand = dict(gen.get("brand") or {})
        palette = dict(brand.get("palette") or {})
        palette["accent"] = ACCENT
        brand["palette"] = palette
        gen["brand"] = brand
        profile.generated_brand = gen

        await db.commit()
        try:
            from app.core.redis import get_redis, Keys
            r = await get_redis()
            await r.delete(Keys.brand(m.id))  # drop cached brand so palette refreshes
        except Exception as e:
            print("redis skip:", e)
        print("accent set to", ACCENT)


if __name__ == "__main__":
    asyncio.run(main())

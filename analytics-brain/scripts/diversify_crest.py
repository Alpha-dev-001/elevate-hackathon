"""One-shot: give the `crest` demo store a genuinely distinct identity so the
side-by-side demo reads as two different stores (not the same gold/Playfair
template). Dark, cool, geometric-sans minimal store. Rebuilds its LayoutDSL from
the new token via the deterministic composer. Idempotent.

Run:  docker compose exec api python scripts/diversify_crest.py
"""
import asyncio

from sqlalchemy import select
from app.core.database import get_session_factory
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import BrandToken
from app.services.layout_dsl import fallback_dsl_from_token

CREST = {
    "colors": {
        "primary": "#0E0F12",
        "accent": "#5B8DEF",       # cool clinical blue — the opposite of haree's gold
        "background": "#0E0F12",    # near-black canvas
        "surface": "#16181D",
        "text": "#F2F3F5",
        "text_muted": "#9AA0A8",
    },
    "typography": {
        "display_font": "Space Grotesk",   # geometric sans (vs haree's Playfair serif)
        "body_font": "Inter",
        "scale": "compact",
        "letter_spacing": "tight",
        "weight": "medium",
    },
    "mood": "minimal-premium",
}


async def main():
    factory = get_session_factory()
    async with factory() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == "crest"))
        if not m:
            print("no merchant 'crest' — nothing to do")
            return
        profile = await db.get(BrandProfileDB, m.id)
        if not profile or not profile.brand_tokens:
            print("crest has no brand_tokens — onboard it first")
            return

        token = BrandToken.model_validate(profile.brand_tokens)
        token.colors = token.colors.model_copy(update=CREST["colors"])
        token.typography = token.typography.model_copy(update=CREST["typography"])
        token.mood = CREST["mood"]
        token.layout = token.layout.model_copy(update={"style": "minimal-dark"})

        # Rebuild the DSL from the new token, then lock dark mode + a card/nav that
        # belong to a dark minimal store (distinct from haree's borderless+underline).
        dsl = fallback_dsl_from_token(token)
        dsl.global_config.color_mode = "dark"
        dsl.global_config.product_card = "hover-reveal-text"
        dsl.global_config.nav_style = "sidebar-text"
        dsl.global_config.corner_radius = "none"
        dsl.global_config.add_to_cart = "card-hover"  # crest: quick-add on hover (haree stays drawer-only)
        dsl.custom_css = (
            '[data-store="crest"] .hero-title { letter-spacing: -0.03em; }\n'
            '[data-store="crest"] .product-card { transition: transform 0.5s cubic-bezier(0.4,0,0.2,1); }\n'
            '[data-store="crest"] .product-card:hover { transform: translateY(-4px); }'
        )
        token.layout_dsl = dsl

        profile.brand_tokens = token.model_dump()
        await db.commit()

        try:
            from app.core.redis import get_redis
            r = await get_redis()
            await r.set(f"layout_dsl:{m.id}", dsl.model_dump_json())
        except Exception as e:
            print("redis cache skip:", e)

        print("crest diversified →",
              "bg", token.colors.background, "accent", token.colors.accent,
              "font", token.typography.display_font,
              "| nav", dsl.global_config.nav_style, "card", dsl.global_config.product_card,
              "sections", [(s.type.value, s.variant) for s in dsl.sections])


if __name__ == "__main__":
    asyncio.run(main())

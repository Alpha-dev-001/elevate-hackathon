"""LayoutDSL engine — Qwen composes the store; this validates, repairs, and
guarantees a renderable result. Three defense layers (A: coerce_variant,
B: normalize_dsl, C: fallback_dsl_from_token) so a garbage Qwen response can
never produce a broken store or a 500 on the demo path."""
from __future__ import annotations

import logging
import re

from app.models.schemas import (
    SectionType, HeroVariant, ProductGridVariant, BannerVariant, StoryVariant,
    NavStyle, ProductCardVariant,
)

logger = logging.getLogger(__name__)

VALID_VARIANTS: dict[SectionType, set[str]] = {
    SectionType.hero: {v.value for v in HeroVariant},
    SectionType.product_grid: {v.value for v in ProductGridVariant},
    SectionType.banner: {v.value for v in BannerVariant},
    SectionType.story: {v.value for v in StoryVariant},
}

DEFAULT_VARIANT: dict[SectionType, str] = {
    SectionType.hero: HeroVariant.editorial_stacked.value,
    SectionType.product_grid: ProductGridVariant.masonry_4col.value,
    SectionType.banner: BannerVariant.static_strip.value,
    SectionType.story: StoryVariant.full_bleed_text.value,
}

# Near-miss → canonical. Keys are normalized (lowercase, non-alnum stripped).
_DSL_COERCE: dict[str, str] = {
    "fullbleedimage": "full-bleed-image", "fullbleed": "full-bleed-image", "hero": "full-bleed-image",
    "editorialstacked": "editorial-stacked", "editorial": "editorial-stacked", "stacked": "editorial-stacked",
    "minimalwordmark": "minimal-wordmark", "wordmark": "minimal-wordmark", "minimal": "minimal-wordmark",
    "split5050": "split-50-50", "split": "split-50-50",
    "masonry4col": "masonry-4col", "masonry": "masonry-4col", "grid": "masonry-4col",
    "featured2col": "featured-2col", "featured": "featured-2col",
    "horizontalscroll": "horizontal-scroll", "scroll": "horizontal-scroll", "carousel": "horizontal-scroll",
    "singlespotlight": "single-spotlight", "spotlight": "single-spotlight",
    "scrollticker": "scroll-ticker", "ticker": "scroll-ticker", "marquee": "scroll-ticker",
    "staticstrip": "static-strip", "strip": "static-strip",
    "announcementbar": "announcement-bar", "announcement": "announcement-bar", "promobar": "announcement-bar",
    "fullbleedtext": "full-bleed-text", "splitimagestory": "split-image-story",
    "imagestory": "split-image-story", "quotecallout": "quote-callout", "quote": "quote-callout",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def coerce_variant(section_type: SectionType, raw: str) -> str:
    """Return a variant guaranteed valid for `section_type`. Cross-type values
    (e.g. a grid variant on a hero) are NEVER honored — they fall back to the
    type default."""
    valid = VALID_VARIANTS[section_type]
    if raw in valid:
        return raw
    coerced = _DSL_COERCE.get(_norm(raw))
    if coerced in valid:
        return coerced
    # normalized exact match against this type's own variants
    nmap = {_norm(v): v for v in valid}
    if _norm(raw) in nmap:
        return nmap[_norm(raw)]
    logger.warning("[dsl] unmapped variant %r for %s → default", raw, section_type.value)
    return DEFAULT_VARIANT[section_type]


# ─── Defense Layer B: structural normalization ───────────────────────────────────

from app.models.schemas import LayoutDSL, LayoutSection, LayoutGlobalConfig

_VALID_NAV = {v.value for v in NavStyle}
_VALID_CARD = {v.value for v in ProductCardVariant}


def _opt(value: object, allowed: tuple[str, ...], default: str) -> str:
    """Keep a value only if it's in the allowed set; else fall to default.
    Used for every optional global-config field so normalize_dsl PRESERVES
    merchant/Qwen choices instead of silently resetting them on re-save."""
    return value if value in allowed else default


def _coerce_global(raw: object) -> LayoutGlobalConfig:
    g = raw if isinstance(raw, dict) else {}
    nav = g.get("nav_style")
    card = g.get("product_card")
    return LayoutGlobalConfig(
        nav_style=nav if nav in _VALID_NAV else NavStyle.underline_tabs.value,
        product_card=card if card in _VALID_CARD else ProductCardVariant.hover_reveal_text.value,
        color_mode=_opt(g.get("color_mode"), ("light", "dark", "auto"), "auto"),
        corner_radius=_opt(g.get("corner_radius"), ("none", "sm", "md", "lg", "full"), "md"),
        density=_opt(g.get("density"), ("sparse", "normal", "dense"), "normal"),
        add_to_cart=_opt(g.get("add_to_cart"), ("drawer-only", "card-hover", "card-always", "none"), "drawer-only"),
        product_detail=_opt(g.get("product_detail"), ("gallery-split", "editorial-stacked", "minimal-centered"), "gallery-split"),
        cart_style=_opt(g.get("cart_style"), ("slide-panel", "full-sheet"), "slide-panel"),
    )


def _clean_sections(raw_sections: object) -> list[LayoutSection]:
    out: list[LayoutSection] = []
    if isinstance(raw_sections, list):
        for s in raw_sections:
            if not isinstance(s, dict):
                continue
            raw_type = s.get("type", "")
            if isinstance(raw_type, SectionType):
                st = raw_type
            else:
                # Accept "hero", "product-grid", and even a stringified enum
                # member ("SectionType.hero") — never silently drop a real section.
                t = str(raw_type).strip().replace("-", "_")
                if "." in t:
                    t = t.rsplit(".", 1)[-1]
                try:
                    st = SectionType(t)
                except ValueError:
                    continue
            variant = coerce_variant(st, str(s.get("variant", "")))
            props = s.get("props") if isinstance(s.get("props"), dict) else {}
            out.append(LayoutSection(type=st, variant=variant, props=props))
    return out


def normalize_dsl(raw: dict) -> LayoutDSL:
    """Defense Layer B. Turn any raw dict into a structurally-safe LayoutDSL."""
    sections = _clean_sections(raw.get("sections"))

    # Rule: at most one hero, and it leads.
    heroes = [s for s in sections if s.type == SectionType.hero]
    non_hero = [s for s in sections if s.type != SectionType.hero]
    sections = ([heroes[0]] if heroes else []) + non_hero

    # Rule: announcement-bar floats above everything (even the hero).
    announce = [s for s in sections if s.type == SectionType.banner and s.variant == "announcement-bar"]
    rest = [s for s in sections if not (s.type == SectionType.banner and s.variant == "announcement-bar")]
    sections = announce[:1] + rest

    # Rule: at least one product_grid.
    if not any(s.type == SectionType.product_grid for s in sections):
        sections.append(LayoutSection(
            type=SectionType.product_grid,
            variant=DEFAULT_VARIANT[SectionType.product_grid],
        ))

    # Rule: no two banners adjacent — drop the second of any adjacent pair.
    deduped: list[LayoutSection] = []
    for s in sections:
        if deduped and deduped[-1].type == SectionType.banner and s.type == SectionType.banner:
            continue
        deduped.append(s)
    sections = deduped

    # Clamp 2..5. Pad with a story if too short.
    if len(sections) < 2:
        sections.append(LayoutSection(type=SectionType.story, variant=DEFAULT_VARIANT[SectionType.story]))
    sections = sections[:5]

    return LayoutDSL(
        sections=sections,
        global_config=_coerce_global(raw.get("global_config")),
        custom_css=str(raw.get("custom_css") or ""),
    )


# ─── Defense Layer C: brand-seeded deterministic fallback ────────────────────────

import hashlib
from app.models.schemas import BrandToken

# Per-style base arrangement (ordered section types) + candidate pools to pick
# from via the brand seed. Each style reads as a different store family.
_STYLE_BLUEPRINT: dict[str, dict] = {
    "editorial": {
        "sections": [SectionType.hero, SectionType.banner, SectionType.product_grid, SectionType.story],
        "hero": ["editorial-stacked", "split-50-50"],
        "grid": ["featured-2col", "masonry-4col"],
        "banner": ["scroll-ticker", "static-strip"],
        "story": ["full-bleed-text", "quote-callout"],
        "nav": ["underline-tabs", "minimal-text"],
        "card": ["editorial-horizontal", "image-below-text", "borderless-floating"],
        "radius": ["none", "sm"],
        "atc": ["drawer-only"],
        "detail": ["editorial-stacked", "gallery-split"],
        "cart": ["slide-panel"],
    },
    "bold-grid": {
        "sections": [SectionType.hero, SectionType.product_grid, SectionType.banner],
        "hero": ["full-bleed-image", "split-50-50"],
        "grid": ["masonry-4col", "featured-2col"],
        "banner": ["static-strip", "announcement-bar"],
        "story": ["split-image-story"],
        "nav": ["pill-nav", "sticky-tabs"],
        "card": ["colored-bg-card", "polaroid-card"],
        "radius": ["lg", "full"],
        "atc": ["card-always", "card-hover"],
        "detail": ["gallery-split", "editorial-stacked"],
        "cart": ["full-sheet", "slide-panel"],
    },
    "minimal-dark": {
        "sections": [SectionType.hero, SectionType.product_grid, SectionType.story],
        "hero": ["minimal-wordmark", "full-bleed-image"],
        "grid": ["horizontal-scroll", "single-spotlight", "masonry-4col"],
        "banner": ["scroll-ticker"],
        "story": ["full-bleed-text"],
        "nav": ["sidebar-text", "minimal-text"],
        "card": ["hover-reveal-text", "borderless-floating"],
        "radius": ["none", "sm"],
        "atc": ["card-hover", "drawer-only"],
        "detail": ["minimal-centered", "gallery-split"],
        "cart": ["slide-panel", "full-sheet"],
    },
    "warm-craft": {
        "sections": [SectionType.banner, SectionType.hero, SectionType.product_grid, SectionType.story],
        "hero": ["split-50-50", "editorial-stacked"],
        "grid": ["masonry-4col", "featured-2col"],
        "banner": ["static-strip", "scroll-ticker"],
        "story": ["split-image-story", "quote-callout"],
        "nav": ["pill-nav", "underline-tabs"],
        "card": ["polaroid-card", "image-below-text"],
        "radius": ["md", "lg"],
        "atc": ["card-hover", "card-always"],
        "detail": ["gallery-split", "editorial-stacked"],
        "cart": ["slide-panel"],
    },
}


def _seed(token: BrandToken) -> int:
    raw = f"{token.store_name}|{token.mood}|{token.industry_hint}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _pick(pool: list[str], seed: int, salt: int) -> str:
    return pool[(seed >> (salt * 3)) % len(pool)]


def fallback_dsl_from_token(token: BrandToken) -> LayoutDSL:
    """Defense Layer C — deterministic, brand-seeded DSL. Guarantees distinct
    stores even when Qwen is unavailable."""
    bp = _STYLE_BLUEPRINT.get(token.layout.style, _STYLE_BLUEPRINT["editorial"])
    seed = _seed(token)

    sections: list[dict] = []
    for i, st in enumerate(bp["sections"]):
        if st == SectionType.hero:
            variant = _pick(bp["hero"], seed, i)
        elif st == SectionType.product_grid:
            variant = _pick(bp["grid"], seed, i)
        elif st == SectionType.banner:
            variant = _pick(bp["banner"], seed, i)
        else:
            variant = _pick(bp["story"], seed, i)
        sections.append({"type": st.value, "variant": variant})

    raw = {
        "sections": sections,
        "global_config": {
            "nav_style": _pick(bp["nav"], seed, 7),
            "product_card": _pick(bp["card"], seed, 5),
            "color_mode": "dark" if token.layout.style == "minimal-dark" else "auto",
            "corner_radius": _pick(bp["radius"], seed, 3),
            "density": "dense" if token.layout.style == "bold-grid" else "normal",
            "add_to_cart": _pick(bp["atc"], seed, 9),
            "product_detail": _pick(bp["detail"], seed, 11),
            "cart_style": _pick(bp["cart"], seed, 13),
        },
        "custom_css": "",
    }
    return normalize_dsl(raw)  # run through Layer B for the structural guarantee


# ─── The Qwen-Max DSL composition call ───────────────────────────────────────────

from app.core.config import get_settings

LAYOUT_DSL_PROMPT = """You are an elite art director composing a UNIQUE storefront layout.
Return ONLY a json object. No prose, no markdown.

You assemble 2-5 ordered sections that feel cohesive for THIS brand's mood and industry.

Section types and their ONLY allowed variants:
- hero: full-bleed-image | editorial-stacked | minimal-wordmark | split-50-50
- product_grid: masonry-4col | featured-2col | horizontal-scroll | single-spotlight
- banner: scroll-ticker | static-strip | announcement-bar
- story: full-bleed-text | split-image-story | quote-callout

global_config:
- nav_style: underline-tabs | pill-nav | sidebar-text | sticky-tabs | minimal-text
- product_card: hover-reveal-text | colored-bg-card | editorial-horizontal | borderless-floating | polaroid-card | image-below-text
- corner_radius: none | sm | md | lg | full
- density: sparse | normal | dense

Rules:
- Exactly ONE hero, and it must be the first section (unless an announcement-bar leads).
- Include at least one product_grid.
- single-spotlight only if product_count <= 10.
- Be OPINIONATED. A luxury beauty brand and a bold streetwear brand must produce
  structurally different stores — different sections, variants, nav, and card.

Return json shaped exactly:
{
  "sections": [{"type": "...", "variant": "...", "props": {}}],
  "global_config": {"nav_style":"...","product_card":"...","corner_radius":"...","density":"..."}
}

Brand:
{brand_json}
product_count: {product_count}
Pure json. Nothing else."""


async def generate_layout_dsl(
    token: BrandToken,
    store_name: str,
    category: str,
    product_count: int,
    *,
    _chat=None,
) -> LayoutDSL:
    """qwen-max composes the store. NEVER raises — any failure (network, non-JSON,
    garbage) falls back to the brand-seeded deterministic DSL."""
    from app.services.brand import _qwen_chat, _extract_json
    import json as _json

    chat = _chat or _qwen_chat
    brand_json = _json.dumps({
        "store_name": store_name, "category": category,
        "mood": token.mood, "industry_hint": token.industry_hint,
        "layout_style": token.layout.style, "brand_voice": token.brand_voice,
    })
    prompt = LAYOUT_DSL_PROMPT.replace("{brand_json}", brand_json).replace("{product_count}", str(product_count))

    try:
        raw = await chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200, temperature=0.7, timeout=60.0,
        )
        data = _extract_json(raw)
        return normalize_dsl(data)
    except Exception as e:  # noqa: BLE001 — fallback must be total for the demo path
        logger.warning("[dsl] generate_layout_dsl falling back to deterministic DSL: %s", e)
        return fallback_dsl_from_token(token)

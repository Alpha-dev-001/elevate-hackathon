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

"""Qwen CSS injection — micro-interaction personality CSS vars can't express.

qwen-max writes ≤15 scoped rules (letter-spacing, hover transforms, transition
timing). We sanitize hard before storage: only rules scoped to this store, no
url()/@import/@keyframes/position:fixed/z-index, only the property allowlist.
The result lands in layout_dsl.custom_css and is injected client-side.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

ALLOWED_PROPS = {
    "transform", "transition", "letter-spacing", "line-height",
    "text-decoration", "opacity", "border-radius", "box-shadow",
    "font-size", "font-weight", "color", "padding", "margin", "gap",
}

_FORBIDDEN = re.compile(r"url\(|@import|@keyframes|position\s*:\s*fixed|z-index", re.I)
# Matches a `property:` occurrence wherever it appears on the line — the
# expected format is one full rule per line (`selector { prop: val; }`), but
# this also tolerates a multi-line rule's bare `prop: val;` line.
_PROP_OCCURRENCE = re.compile(r"([a-zA-Z-]+)\s*:")


def sanitize_css(css: str, slug: str) -> str:
    """Keep only lines scoped to this store, where every declared property is
    on ALLOWED_PROPS, with nothing forbidden. Line-based (matches the spec) —
    generated CSS is one full rule per line. A line naming any property NOT
    on ALLOWED_PROPS is dropped whole — this was previously declared but
    never actually checked, so any property Qwen wrote passed through
    untouched."""
    if not css:
        return ""
    scope = f'[data-store="{slug}"]'
    safe: list[str] = []
    for line in css.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _FORBIDDEN.search(stripped):
            continue
        if stripped in ("}", "{"):
            safe.append(stripped)
            continue
        if scope not in stripped:
            continue  # unscoped selector/rule — drop
        props = _PROP_OCCURRENCE.findall(stripped)
        if props and not all(p.lower() in ALLOWED_PROPS for p in props):
            continue
        safe.append(stripped)
    return "\n".join(safe)


CSS_PROMPT = """Based on this brand's mood ({mood}) and spatial personality ({spatial}),
generate a small CSS block (max 15 rules) expressing this brand's micro-interaction
character. Return ONLY the css — no prose, no json, no markdown.

Use ONLY these selectors:
  [data-store="{slug}"] .product-card
  [data-store="{slug}"] .product-card:hover
  [data-store="{slug}"] .hero-title
  [data-store="{slug}"] .section-banner
  [data-store="{slug}"] .product-price
  [data-store="{slug}"] .nav-links
  [data-store="{slug}"] .nav-link

Use ONLY these properties: transform, transition, letter-spacing, line-height,
text-decoration, opacity, border-radius, box-shadow, font-size, font-weight,
color, padding, margin, gap.

NOTE (2026-07-12): only .nav-links/.nav-link currently exist in the real
DOM — the product-card/hero-title/section-banner/product-price selectors
above have never been added to any component and any CSS targeting them is
a silent no-op. Kept in the prompt so this feature's original intended
scope isn't silently narrowed; see UPGRADES.md for the follow-up to add
real hooks for the rest.
No url(), no position: fixed, no z-index, no @keyframes, no @import.
One rule per line. Return ONLY the CSS."""


async def generate_custom_css(token, slug: str, *, _chat=None) -> str:
    """qwen-max writes the scoped CSS. NEVER raises — returns "" on any failure."""
    from app.services.brand import _qwen_chat
    from app.core.config import get_settings

    chat = _chat or _qwen_chat
    prompt = (
        CSS_PROMPT
        .replace("{mood}", token.mood)
        .replace("{spatial}", token.layout.style)
        .replace("{slug}", slug)
    )
    try:
        raw = await chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600, temperature=0.6, timeout=45.0,
            json_mode=False,  # CSS, not JSON
        )
        return sanitize_css(raw, slug)
    except Exception as e:  # noqa: BLE001
        logger.warning("[css] generate_custom_css failed for %s: %s", slug, e)
        return ""

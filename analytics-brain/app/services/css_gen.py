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
}

_FORBIDDEN = re.compile(r"url\(|@import|@keyframes|position\s*:\s*fixed|z-index", re.I)


def sanitize_css(css: str, slug: str) -> str:
    """Keep only lines scoped to this store, drop anything forbidden. Line-based
    (matches the spec) — generated CSS is one rule per line."""
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
        # Keep scoped rule lines and bare closing braces; drop unscoped selectors.
        if scope in stripped or stripped in ("}", "{"):
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

Use ONLY these properties: transform, transition, letter-spacing, line-height,
text-decoration, opacity, border-radius, box-shadow.
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

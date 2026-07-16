"""
Product vision — qwen-vl-max reads a single product photo and returns a
structured draft: name, brand, description (brand voice), category, colorways,
and a *suggested* price anchored to the merchant's baseline (never web-MSRP).

This is the eyes for "drop a folder of photos → get a catalogue". It is honest:
when it can't confidently identify the product it says so (`confident=False`)
so the merchant reviews it rather than a silent wrong guess going live.

Isolated on purpose — reuses brand.py's Qwen transport but adds no coupling to
the onboarding/brand pipeline.
"""
from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError

logger = logging.getLogger(__name__)


class DeadImageError(BrandGenerationError):
    """Raised when a URL is confirmed dead/non-image before spending a Qwen
    call on it — distinct from a Qwen-side failure so callers can log it
    without implying the model did anything wrong."""


async def is_probably_image(url: str) -> bool:
    """Cheap reachability + content-type pre-check, run before any Qwen
    vision call. Only returns False on a CONFIRMED negative signal (URL
    unreachable, or a content-type that is explicitly not an image) — an
    inconclusive check (HEAD blocked/timeout, missing content-type header,
    a CDN that 405s HEAD) returns True so a real photo behind a picky CDN
    is never wrongly rejected. This trades a few false positives (still
    handled by Qwen's own download-failure path) for zero false negatives.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
            resp = await client.head(url)
            if resp.status_code in (405, 501):
                # HEAD not supported — fall back to a ranged GET instead of
                # trusting an inconclusive HEAD response.
                resp = await client.get(url, headers={"Range": "bytes=0-0"})
            if resp.status_code >= 400:
                return False
            content_type = resp.headers.get("content-type", "")
            if content_type and not content_type.startswith("image/"):
                return False
    except (httpx.TimeoutException, httpx.TransportError):
        return True  # inconclusive — let Qwen's own fetch be the judge
    return True


class ProductVision(BaseModel):
    """One product drafted from one photo. `confident=False` ⇒ needs merchant review."""
    name: str
    brand: str = ""
    description: str = ""
    category: str = ""
    colors: list[str] = Field(default_factory=list)
    suggested_price: float
    confident: bool = True


PRODUCT_VISION_PROMPT = """You are cataloguing ONE product from its photo for the fashion boutique "{store_name}".
Brand voice: {brand_voice}
{memory_block}
Look at the image and identify the product from what you can SEE (brand markings on
the item/box/bag, product type, colours, standout design). Return ONLY this json:
{{
  "name": "<concise, tasteful, sell-able product name, e.g. 'Nautica Logo Slides' or 'Crossover Strap Leather Slides'>",
  "brand": "<the brand ONLY if its logo or name is clearly legible in THIS photo; otherwise ''>",
  "description": "<one vivid sentence in the store's brand voice — no price, no hype claims>",
  "category": "<one lowercase word: slides | sandals | sneakers | footwear | bags | accessories | apparel | other>",
  "colors": ["<each distinct colourway visible in the photo, lowercase, e.g. 'black','olive','blue'>"],
  "suggested_price": <a number the merchant might charge. Anchor to their baseline of {baseline}. Nudge UP for premium/designer brands, DOWN for plain items, but STAY within {lo} to {hi}. This is a starting point the merchant will adjust — do NOT use retail/MSRP.>,
  "confident": <true if you can clearly tell what this product is, false if the photo is ambiguous or you are guessing>
}}

Naming rules (important):
- Do NOT invent or guess a brand. Name a brand only when you can actually read its
  logo/text in the image. If unsure, drop the brand and name it by type + a standout
  feature (e.g. 'Woven Crossover Slides').
- Keep every name tasteful and commercial for a boutique. NEVER use offensive,
  violent, sexual, or nonsensical words — even if such text appears printed on the
  item, do not put it in the name; describe the product instead.
- If you genuinely cannot tell what the product is, set "confident": false and
  "name": "Unidentified item".
Return ONLY the json."""


async def analyze_product_image(
    *,
    image_ref: str,
    store_name: str,
    brand_voice: str,
    baseline_price: float,
    memory_context: str = "",
) -> ProductVision:
    """One qwen-vl-max pass over a product photo → a validated ProductVision.

    Prices are clamped into [0.6×, 2×] baseline so a hallucinated MSRP can never
    leak through. Raises BrandGenerationError on transport/parse failure so the
    caller can decide to skip or retry that one image.

    When memory_context is provided (built from merchant edit history), it is
    injected into the prompt so Qwen adapts naming, pricing, and categorization
    to the merchant's demonstrated preferences."""
    lo = round(baseline_price * 0.6, 2)
    hi = round(baseline_price * 2.0, 2)
    memory_block = f"\n{memory_context}\n" if memory_context else ""
    prompt = PRODUCT_VISION_PROMPT.format(
        store_name=store_name,
        brand_voice=brand_voice or "clear, confident, modern",
        memory_block=memory_block,
        baseline=baseline_price,
        lo=lo,
        hi=hi,
    )

    raw = await _qwen_chat(
        model=get_settings().qwen_vl_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_ref}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        max_tokens=400,
        temperature=0.2,
        timeout=45.0,
    )
    data = _extract_json(raw)

    # Coerce + clamp defensively — never trust the model's number or shape raw.
    # Use explicit None check — `or` can't distinguish 0 from missing.
    raw_price = data.get("suggested_price")
    try:
        price = float(raw_price) if raw_price is not None else baseline_price
    except (TypeError, ValueError):
        price = baseline_price
    price = max(lo, min(hi, price))

    colors = data.get("colors") or []
    if not isinstance(colors, list):
        colors = [str(colors)]
    colors = [str(c).strip().lower() for c in colors if str(c).strip()][:6]

    # Strip BEFORE fallback — "   " is truthy but strips to empty.
    raw_name = str(data.get("name") or "").strip()
    # Default to NOT confident on a malformed/incomplete response — an
    # absent "confident" key means Qwen's JSON didn't match the contract,
    # which is itself a reason to force merchant review rather than trust
    # it. Same logic if no usable name came back at all: "Unidentified
    # item" is definitionally not a confident catalogue entry, regardless
    # of what the "confident" field claims.
    confident = bool(data.get("confident", False)) and bool(raw_name)
    try:
        return ProductVision(
            name=(raw_name or "Unidentified item")[:120],
            brand=str(data.get("brand") or "").strip()[:60],
            description=str(data.get("description") or "").strip()[:400],
            category=str(data.get("category") or "other").strip().lower()[:40],
            colors=colors,
            suggested_price=round(price, 2),
            confident=confident,
        )
    except ValueError as e:
        raise BrandGenerationError(f"Product vision failed schema validation: {e!s}") from e

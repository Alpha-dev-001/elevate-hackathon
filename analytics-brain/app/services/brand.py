"""
The brand engine — Qwen is the brain, this is the wiring.

Two Qwen calls, two models, in sequence:
  1. qwen-vl-max  — looks at the logo (by OSS URL), returns LogoAnalysis
  2. qwen-max     — turns that into a full BrandPackage: brand + guard rules + SVG

FastAPI never touches file bytes. The frontend uploads the logo to OSS and
hands us a URL string; qwen-vl-max reads the image straight from that URL.

Every Qwen call here is hardened: transient failures retry with backoff,
malformed JSON is repaired-or-surfaced (never silently swallowed), and SVG
output is sanitized with a deterministic fallback so the brand always
validates even if Qwen flakes on the icon markup.

Redis caching of the finished package is the onboarding router's job (it owns
merchant_id) — this module stays pure and independently testable, so the
"Redis is down" failure mode can't take the brand engine with it.
"""
from __future__ import annotations

import asyncio
import json
import re
import html

import httpx

from app.core.config import get_settings
from app.models.schemas import (
    LogoAnalysis,
    GeneratedBrand,
    BrandGuardRules,
    BrandGuardRule,
    BrandPackage,
    BrandIconSet,
    BrandPalette,
    ProductCSVRow,
)


class BrandGenerationError(Exception):
    """Raised when a Qwen call fails or returns output we can't trust.

    The router catches this and surfaces a real error to the merchant —
    a half-built brand is worse than an honest failure.
    """


# ─── Prompts ──────────────────────────────────────────────────────────────────
# NOTE: every prompt MUST contain the literal word "json" — DashScope rejects
# response_format=json_object with a 400 otherwise.

LOGO_ANALYSIS_PROMPT = """You are a brand designer's trained eye. Look at this store logo.

Return ONLY a JSON object with exactly these fields — no prose, no markdown:

{
  "primary_colors": ["#hex", "#hex"],     // dominant brand colors, extracted directly from the image
  "secondary_colors": ["#hex"],            // supporting colors, may be empty
  "mood": "one or two words, e.g. 'bold', 'minimalist', 'playful', 'luxury'",
  "style": "one or two words, e.g. 'geometric', 'organic', 'vintage', 'modern'",
  "geometry_notes": "one sentence on shapes, lines, symmetry, weight"
}

Extract hex colors precisely from the actual pixels — do not guess generic values.
Pure JSON. Nothing else."""


BRAND_GENERATION_PROMPT = """You are the AI that designs and then DEFENDS a store's brand.

You receive a logo analysis and store details. You return a complete brand
package as a single JSON object. You are not chatting — your output is parsed
by a machine. Return ONLY JSON, no prose, no markdown fences.

Schema (every field required):

{
  "store_name": "the store's name, unchanged",
  "tagline": "short, punchy, on-brand — under 8 words",
  "palette": {
    "primary":    "#hex",
    "secondary":  "#hex",
    "accent":     "#hex",
    "background":  "#hex — the store's page background, usually dark or near-white",
    "text":       "#hex — readable against background"
  },
  "typography": {
    "display_font": "a real Google Font name for headings",
    "body_font":    "a real Google Font name for body text"
  },
  "brand_voice_profile": "2-3 sentences describing the tone of voice for this store's copy — used later to write product descriptions. Be specific to THIS brand.",
  "icons": {
    "logo_mark":  "<svg ...>...</svg> — a SIMPLE geometric logo mark, viewBox 0 0 64 64, using palette colors, no text, no external refs, under 600 chars",
    "store_icon": "<svg ...>...</svg> — a SIMPLE favicon, viewBox 0 0 32 32, single shape, palette colors, under 400 chars"
  },
  "layout_variant": "standard | promo_heavy | minimal",
  "suggested_categories": ["2 to 4 product category names that fit this store"],
  "guards": {
    "allowed_color_palette": ["#hex", "#hex", "#hex"],
    "forbidden_combinations": ["short human sentence naming two colors that must not sit together for THIS brand"],
    "rules": [
      {
        "rule_id": "accent_lock",
        "field": "accent",
        "description": "what this rule protects, plainly",
        "warning_message": "FIRST PERSON, as the AI that built this brand. Reference the SPECIFIC hex you chose and WHY. Example: 'I chose #6EE7B7 as your accent because it lifts off the deep navy in your logo. Swapping it for a warm yellow collapses the cool tension that makes this brand feel premium.' Defend your own work — never generic."
      }
    ]
  }
}

Rules for the guards block — this is the brand's immune system:
- "rules" MUST be a JSON array of OBJECTS, each with the four keys rule_id,
  field, description, warning_message. NEVER a flat list of "key: value"
  strings. Each rule is its own {...} object.
- allowed_color_palette = the hexes you actually used in palette, the only safe set.
- Author one rule per protected field you care about (accent, primary, background, layout_variant). 1 to 4 rules.
- Each warning_message is written in YOUR voice, references the real hex values,
  and explains the consequence of breaking it for THIS specific logo and mood.
- The SVG icons must be minimal geometric marks. Simple paths, rects, circles.
  No <script>, no <image>, no external href. Inline fills only.

Make every word specific to the logo analysis and store details you were given.
Pure JSON. Nothing else."""


# ─── HTTP plumbing ──────────────────────────────────────────────────────────────

# Retry only on transient failures. A 4xx (bad request, bad key) is permanent —
# retrying just burns the demo clock.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


async def _qwen_chat(
    *,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    json_mode: bool = True,
    timeout: float = 30.0,
    attempts: int = 3,
) -> str:
    """One Qwen chat-completion call with bounded exponential backoff.

    Returns the raw assistant message string. Raises BrandGenerationError on
    permanent failure or after exhausting transient retries.
    """
    settings = get_settings()
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    url = f"{settings.qwen_api_base}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.qwen_api_key}"}

    last_err: str = "unknown error"
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(attempts):
            try:
                resp = await client.post(url, headers=headers, json=payload)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_err = f"network error: {e!s}"
            else:
                if resp.status_code == 200:
                    try:
                        return resp.json()["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, json.JSONDecodeError) as e:
                        raise BrandGenerationError(
                            f"{model} returned an unexpected envelope: {e!s}"
                        ) from e
                # Permanent client errors: surface immediately, do not retry.
                if resp.status_code not in _RETRYABLE_STATUS:
                    raise BrandGenerationError(
                        f"{model} call failed [{resp.status_code}]: {resp.text[:300]}"
                    )
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"

            # transient — back off and retry (0.5s, 1s, ...), unless last attempt
            if attempt < attempts - 1:
                await asyncio.sleep(0.5 * (2 ** attempt))

    raise BrandGenerationError(
        f"{model} call failed after {attempts} attempts — last: {last_err}"
    )


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _extract_json(raw: str) -> dict:
    """Parse Qwen output into a dict, tolerating stray markdown fences.

    json_object mode usually returns clean JSON, but vision models in
    particular sometimes wrap it. We strip fences, and if that still fails
    we isolate the outermost {...} block before giving up.
    """
    if not raw or not raw.strip():
        raise BrandGenerationError("Qwen returned an empty response")

    candidate = _FENCE_RE.sub("", raw.strip())
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise BrandGenerationError(
        f"Qwen returned non-JSON output: {raw[:200]}"
    )


# ─── SVG safety + fallback ──────────────────────────────────────────────────────

_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_FOREIGN_RE = re.compile(r"<foreignObject[^>]*>.*?</foreignObject>", re.DOTALL | re.IGNORECASE)
_ON_HANDLER_RE = re.compile(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", re.IGNORECASE)
_EXTERNAL_REF_RE = re.compile(r"(?:xlink:)?href\s*=\s*(\"[^\"]*\"|'[^']*')", re.IGNORECASE)
_SVG_TAG_RE = re.compile(r"<svg[\s>]", re.IGNORECASE)
_SVG_SHAPE_RE = re.compile(
    r"<(?:rect|circle|ellipse|line|polyline|polygon|path|text)[\s/>]", re.IGNORECASE
)


def sanitize_svg(svg: str) -> str:
    """Strip anything executable or externally-referencing from Qwen SVG.

    Icons are served as static assets and injected into the DOM, so a
    <script> or an external href in here would be a live XSS vector.
    """
    svg = _SCRIPT_RE.sub("", svg)
    svg = _FOREIGN_RE.sub("", svg)
    svg = _ON_HANDLER_RE.sub("", svg)
    svg = _EXTERNAL_REF_RE.sub("", svg)
    return svg.strip()


def _is_usable_svg(svg: str | None) -> bool:
    """A sanitized string is usable only if it still looks like a real <svg>."""
    if not svg or not isinstance(svg, str):
        return False
    s = svg.strip()
    return (
        bool(_SVG_TAG_RE.search(s))
        and "</svg>" in s.lower()
        and bool(_SVG_SHAPE_RE.search(s))  # must actually draw something
        and len(s) < 4000
    )


def _fallback_mark(initial: str, bg: str, fg: str, size: int) -> str:
    """A deterministic on-brand SVG mark — store initial on a palette tile.

    Used when Qwen omits or mangles an icon. Guarantees GeneratedBrand
    validates and the storefront's zero-product state still looks intentional.
    """
    initial = html.escape(initial[:1].upper() or "E")
    bg = html.escape(bg)
    fg = html.escape(fg)
    r = max(4, size // 8)
    fs = int(size * 0.55)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'width="{size}" height="{size}" role="img">'
        f'<rect width="{size}" height="{size}" rx="{r}" fill="{bg}"/>'
        f'<text x="50%" y="50%" dy="0.07em" text-anchor="middle" '
        f'dominant-baseline="central" font-family="sans-serif" font-weight="700" '
        f'font-size="{fs}" fill="{fg}">{initial}</text></svg>'
    )


def _safe_icons(raw_icons: object, store_name: str, palette: BrandPalette) -> BrandIconSet:
    """Sanitize Qwen's icons; fall back deterministically per-icon on failure."""
    raw_icons = raw_icons if isinstance(raw_icons, dict) else {}

    logo_raw = raw_icons.get("logo_mark")
    logo_clean = sanitize_svg(logo_raw) if isinstance(logo_raw, str) else ""
    if not _is_usable_svg(logo_clean):
        logo_clean = _fallback_mark(store_name, palette.primary, palette.background, 64)

    icon_raw = raw_icons.get("store_icon")
    icon_clean = sanitize_svg(icon_raw) if isinstance(icon_raw, str) else ""
    if not _is_usable_svg(icon_clean):
        icon_clean = _fallback_mark(store_name, palette.accent, palette.background, 32)

    return BrandIconSet(logo_mark=logo_clean, store_icon=icon_clean)


# ─── 1. The eyes — qwen-vl-max ──────────────────────────────────────────────────

async def analyze_logo(logo_url: str) -> LogoAnalysis:
    """qwen-vl-max reads the logo straight from its OSS URL.

    No bytes pass through FastAPI — the model fetches the public image itself.
    """
    if not logo_url or not logo_url.strip():
        raise BrandGenerationError("analyze_logo called without a logo URL")

    raw = await _qwen_chat(
        model=get_settings().qwen_vl_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": logo_url}},
                    {"type": "text", "text": LOGO_ANALYSIS_PROMPT},
                ],
            }
        ],
        max_tokens=512,
        temperature=0.1,  # near-deterministic — we want stable color extraction
        timeout=30.0,
    )

    data = _extract_json(raw)
    try:
        return LogoAnalysis.model_validate(data)
    except ValueError as e:
        raise BrandGenerationError(f"Logo analysis failed schema validation: {e!s}") from e


# ─── 2. The brain — qwen-max ────────────────────────────────────────────────────

async def generate_brand(
    analysis: LogoAnalysis,
    store_name: str,
    category: str,
    description: str,
) -> tuple[GeneratedBrand, BrandGuardRules]:
    """qwen-max turns the logo analysis into a brand + its own defense rules.

    One call, maximum work: palette, typography, voice, SVG icons, and the
    pre-authored BrandGuardRules that fire later with zero round-trip.
    """
    context = json.dumps(
        {
            "store_name": store_name,
            "category": category,
            "description": description,
            "logo_analysis": analysis.model_dump(),
        }
    )

    raw = await _qwen_chat(
        model=get_settings().qwen_model,
        messages=[
            {"role": "system", "content": BRAND_GENERATION_PROMPT},
            {"role": "user", "content": context},
        ],
        max_tokens=3000,  # SVG markup is token-heavy
        temperature=0.4,
        timeout=45.0,
    )

    data = _extract_json(raw)

    # Force store_name to the merchant's real value — never let Qwen rename them.
    data["store_name"] = store_name

    palette = _coerce_palette(data.get("palette"), analysis)
    data["palette"] = palette.model_dump()
    data["icons"] = _safe_icons(data.get("icons"), store_name, palette).model_dump()

    try:
        brand = GeneratedBrand.model_validate(data)  # extra "guards" key ignored
    except ValueError as e:
        raise BrandGenerationError(f"Brand failed schema validation: {e!s}") from e

    guards = _coerce_guards(data.get("guards"), palette)
    return brand, guards


def _coerce_palette(raw_palette: object, analysis: LogoAnalysis) -> BrandPalette:
    """Validate Qwen's palette; backfill any missing slot from the logo colors.

    A single missing hex shouldn't sink the whole brand — we patch from the
    analysis and sane defaults so the package always validates.
    """
    p = raw_palette if isinstance(raw_palette, dict) else {}
    primaries = analysis.primary_colors or ["#6EE7B7"]
    seconds = analysis.secondary_colors or primaries

    def pick(key: str, default: str) -> str:
        v = p.get(key)
        return v if isinstance(v, str) and v.strip().startswith("#") else default

    return BrandPalette(
        primary=pick("primary", primaries[0]),
        secondary=pick("secondary", seconds[0] if seconds else primaries[0]),
        accent=pick("accent", primaries[-1]),
        background=pick("background", "#0A0A0B"),
        text=pick("text", "#FFFFFF"),
    )


_RULE_KEYS = ("rule_id", "field", "description", "warning_message")


def _parse_flat_rules(items: list) -> list[dict]:
    """Reassemble Qwen's flattened 'key: value' rule strings into rule dicts.

    qwen-max sometimes emits rules as ["rule_id: x", "field: accent",
    "warning_message: ..."] instead of an array of objects. The content is
    good — only the shape is wrong. We rebuild objects, splitting on each
    new 'rule_id' boundary. partition() keeps colons inside the value (hex
    values, sentences) intact.
    """
    rules: list[dict] = []
    current: dict = {}
    for s in items:
        if not isinstance(s, str) or ":" not in s:
            continue
        key, _, val = s.partition(":")
        key = key.strip().lower().lstrip("-* ").strip()
        if key not in _RULE_KEYS:
            continue
        if key == "rule_id" and current:
            rules.append(current)
            current = {}
        current[key] = val.strip().strip('",')
    if current:
        rules.append(current)
    return rules


def _normalize_rules(raw_rules: object) -> list[dict]:
    """Coerce whatever Qwen returned for `rules` into valid rule dicts.

    Keeps only rules that carry a warning_message — a guard with no message
    is useless to the interceptor. Backfills the other required fields so the
    recovered message still validates.
    """
    if not isinstance(raw_rules, list) or not raw_rules:
        return []

    if all(isinstance(r, str) for r in raw_rules):
        candidates = _parse_flat_rules(raw_rules)
    else:
        candidates = [r for r in raw_rules if isinstance(r, dict)]

    out: list[dict] = []
    for i, r in enumerate(candidates):
        msg = r.get("warning_message")
        if not isinstance(msg, str) or not msg.strip():
            continue  # no message -> no point keeping it
        out.append(
            {
                "rule_id": str(r.get("rule_id") or f"brand_rule_{i + 1}"),
                "field": str(r.get("field") or "accent"),
                "description": str(r.get("description") or "Protects a brand decision."),
                "warning_message": msg.strip(),
            }
        )
    return out


def _normalize_forbidden(raw: object) -> list[str]:
    """forbidden_combinations may come back as strings or as {a,b,reason} dicts."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            a = item.get("color_a") or item.get("a")
            b = item.get("color_b") or item.get("b")
            reason = item.get("reason") or ""
            if a and b:
                out.append(f"{a} and {b} clash" + (f": {reason}" if reason else ""))
    return out


def _coerce_guards(raw_guards: object, palette: BrandPalette) -> BrandGuardRules:
    """Validate the guard block; repair Qwen's structural quirks; never return
    a guard with no rule.

    The interceptor must always have something to defend with — and we work
    hard to keep Qwen's *own* warning words rather than dropping to the
    deterministic fallback, because that message is the brand's voice.
    """
    palette_hexes = [
        palette.primary, palette.secondary, palette.accent,
        palette.background, palette.text,
    ]

    g = raw_guards if isinstance(raw_guards, dict) else {}
    allowed = g.get("allowed_color_palette")
    if not isinstance(allowed, list) or not allowed:
        allowed = palette_hexes

    rules = _normalize_rules(g.get("rules"))
    if not rules:
        # Last resort only — Qwen gave us nothing usable.
        rules = [_default_accent_rule(palette).model_dump()]

    try:
        return BrandGuardRules.model_validate(
            {
                "allowed_color_palette": [str(c) for c in allowed],
                "forbidden_combinations": _normalize_forbidden(g.get("forbidden_combinations")),
                "rules": rules,
            }
        )
    except ValueError:
        # Belt and suspenders — a clean minimal guard beats a 500.
        return BrandGuardRules(
            allowed_color_palette=palette_hexes,
            forbidden_combinations=[],
            rules=[_default_accent_rule(palette)],
        )


def _default_accent_rule(palette: BrandPalette) -> BrandGuardRule:
    """A plain accent-lock rule for when Qwen returns no usable guards."""
    return BrandGuardRule(
        rule_id="accent_lock",
        field="accent",
        description="Protects the accent color chosen to match the logo.",
        warning_message=(
            f"I chose {palette.accent} as your accent to sit against "
            f"{palette.background}. Changing it risks breaking the contrast "
            f"balance I built this brand around."
        ),
    )


# ─── Orchestrator ───────────────────────────────────────────────────────────────

async def build_brand_package(
    logo_url: str,
    store_name: str,
    category: str,
    description: str,
) -> BrandPackage:
    """Full pipeline: logo URL -> LogoAnalysis -> BrandPackage.

    Sequential by necessity — the brain needs the eyes' output. Caching the
    result in Redis is the caller's responsibility.
    """
    analysis = await analyze_logo(logo_url)
    brand, guards = await generate_brand(analysis, store_name, category, description)
    return BrandPackage(analysis=analysis, brand=brand, guards=guards)


# ─── Product descriptions — one batched call, never a loop ───────────────────────

async def generate_descriptions(
    products: list[ProductCSVRow],
    brand_voice_profile: str,
) -> dict[str, str]:
    """Write all product descriptions in ONE qwen-max call.

    CLAUDE.md is explicit: never loop Qwen per product. Returns a
    {product_name: description} map. Any product the model misses is filled
    with a safe brand-neutral line so no product ships description-less.
    """
    if not products:
        return {}

    catalogue = [
        {"name": p.name, "category": p.category or "general", "price": p.price}
        for p in products
    ]

    prompt = f"""You are writing product descriptions for an online store.

Brand voice to match exactly:
{brand_voice_profile}

Write a 2-3 sentence description for each product below. Match the brand voice.
No headers, no bullet points, no markdown — just the sentences.

Return ONLY a JSON object mapping each product name to its description:
{{ "Product Name": "description...", ... }}

Products:
{json.dumps(catalogue, ensure_ascii=False)}"""

    raw = await _qwen_chat(
        model=get_settings().qwen_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=min(3500, 220 * len(products) + 300),
        temperature=0.6,
        timeout=45.0,
    )

    data = _extract_json(raw)
    result: dict[str, str] = {}
    for p in products:
        desc = data.get(p.name)
        if isinstance(desc, str) and desc.strip():
            result[p.name] = desc.strip()
        else:
            # No silent gap — every product gets a usable line.
            result[p.name] = f"{p.name} — a considered addition to the collection."
    return result

import httpx
import json
import base64
from app.core.config import get_settings
from app.models.schemas import (
    LogoAnalysis, GeneratedBrand, BrandPalette,
    BrandGuardRules, ColorCombo, FontPairing,
    LogoStyle, ColorTemp, FontPersonality, LayoutVariant
)

LOGO_ANALYSIS_PROMPT = """Analyze this store logo and return ONLY a JSON object with this exact schema:

{
  "dominant_colors": ["#hex1", "#hex2", "#hex3"],
  "style": "minimal | bold | playful | luxury | corporate",
  "mood": "short phrase describing emotional feel",
  "color_temperature": "warm | cool | neutral",
  "font_personality": "serif | sans | display | mono",
  "contrast_ratio": 4.5
}

Be precise about hex colors — extract them directly from the image.
No prose. No markdown. Pure JSON."""

BRAND_GENERATION_PROMPT = """You are a brand designer and business intelligence system.

Given this logo analysis and store information, generate a complete brand package.
Return ONLY a JSON object matching this exact schema — no prose, no markdown:

{
  "color_palette": {
    "primary": "#hex",
    "accent": "#hex",
    "background": "#hex",
    "surface": "#hex",
    "text": "#hex",
    "text_muted": "#hex"
  },
  "tagline": "short punchy tagline",
  "hero_copy": "one compelling sentence for the hero banner",
  "layout_variant": "standard | promo_heavy | minimal",
  "suggested_categories": ["cat1", "cat2", "cat3"],
  "font_pairing": {
    "display": "font name for headings",
    "body": "font name for body text"
  },
  "brand_guard_rules": {
    "protected_colors": ["#hex1"],
    "forbidden_combinations": [
      {
        "color_a": "#hex",
        "color_b": "#hex", 
        "reason": "specific reason these clash for THIS brand"
      }
    ],
    "warm_cool_lock": "warm | cool | neutral | null",
    "min_contrast_ratio": 4.5,
    "protected_layout_elements": ["hero_image", "logo_position"],
    "forbidden_layout_variants": [],
    "tone_keywords": ["keyword1", "keyword2"],
    "forbidden_tone_keywords": ["keyword1"],
    "color_warning_template": "Write in first person as the AI that built this brand. Reference the SPECIFIC hex values you chose and WHY. Example: I chose #6EE7B7 because it contrasts with the deep navy in your logo. Changing this to a warm yellow destroys the temperature balance I established. Make it personal — you are defending your own work, not issuing a generic alert."
  }
}

The brand_guard_rules must be SPECIFIC to this brand — not generic advice.
Reference the actual logo colors, style, and mood in your reasoning.
The color_warning_template will be shown to the merchant when they try to break brand rules.
Make it feel like Qwen is protecting something it built, not issuing a generic alert."""


async def analyze_logo(logo_image_bytes: bytes, content_type: str) -> LogoAnalysis:
    """
    Uses Qwen-VL (multimodal) to analyze an uploaded logo.
    Extracts colors, style, mood — the raw material for brand generation.
    """
    settings = get_settings()
    image_b64 = base64.b64encode(logo_image_bytes).decode()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.qwen_api_base}/chat/completions",
            headers={"Authorization": f"Bearer {settings.qwen_api_key}"},
            json={
                "model": settings.qwen_vl_model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{content_type};base64,{image_b64}"
                                }
                            },
                            {
                                "type": "text",
                                "text": LOGO_ANALYSIS_PROMPT
                            }
                        ]
                    }
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 512,
                "temperature": 0.1,  # very low — we want consistent color extraction
            },
        )
        response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]
    return LogoAnalysis.model_validate_json(raw)


async def generate_brand(
    logo_analysis: LogoAnalysis,
    store_name: str,
    category: str,
    description: str,
) -> GeneratedBrand:
    """
    Uses Qwen-Max to generate a full brand package including BrandGuardRules.
    The guard rules are Qwen's self-authored defense of what it built.
    """
    settings = get_settings()

    context = json.dumps({
        "store_name": store_name,
        "category": category,
        "description": description,
        "logo_analysis": logo_analysis.model_dump(),
    })

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            f"{settings.qwen_api_base}/chat/completions",
            headers={"Authorization": f"Bearer {settings.qwen_api_key}"},
            json={
                "model": settings.qwen_model,
                "messages": [
                    {"role": "system", "content": BRAND_GENERATION_PROMPT},
                    {"role": "user", "content": context},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 2048,
                "temperature": 0.4,
            },
        )
        response.raise_for_status()

    raw = response.json()["choices"][0]["message"]["content"]
    return GeneratedBrand.model_validate_json(raw)


async def generate_product_description(
    product_name: str,
    category: str,
    brand_context: GeneratedBrand,
) -> str:
    """
    Qwen writes a product description consistent with the store's brand voice.
    Uses tone_keywords from BrandGuardRules to stay on-brand.
    """
    settings = get_settings()

    prompt = f"""Write a product description for "{product_name}" in the {category} category.

Brand voice: {", ".join(brand_context.brand_guard_rules.tone_keywords)}
Avoid: {", ".join(brand_context.brand_guard_rules.forbidden_tone_keywords)}
Store tagline context: {brand_context.tagline}

Return 2-3 sentences only. No headers. No bullet points. Just the description."""

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{settings.qwen_api_base}/chat/completions",
            headers={"Authorization": f"Bearer {settings.qwen_api_key}"},
            json={
                "model": settings.qwen_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150,
                "temperature": 0.6,
            },
        )
        response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"].strip()

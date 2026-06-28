import json
import asyncio
from app.services.layout_dsl import generate_layout_dsl
from app.models.schemas import (
    BrandToken, BrandColors, BrandTypographyToken, BrandLayoutToken, LayoutDSL,
    SectionType, HeroVariant,
)

_HERO_VALUES = {v.value for v in HeroVariant}


def _token():
    return BrandToken(
        store_name="Haree", tagline="t",
        colors=BrandColors(primary="#000", accent="#6EE7B7", background="#0A0A0B", surface="#111", text="#fff", text_muted="#999"),
        typography=BrandTypographyToken(display_font="Syne", body_font="Inter"),
        layout=BrandLayoutToken(style="editorial", hero_type="split", product_grid="masonry",
                                card_style="borderless", border_radius="8px", spacing="balanced", category_style="pill"),
        mood="refined", industry_hint="beauty", brand_voice="quiet",
    )


def test_valid_qwen_output_parsed():
    async def fake_chat(**kw):
        return json.dumps({
            "sections": [
                {"type": "hero", "variant": "editorial-stacked"},
                {"type": "product_grid", "variant": "featured-2col"},
            ],
            "global_config": {"nav_style": "underline-tabs", "product_card": "editorial-horizontal"},
        })
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=fake_chat))
    assert isinstance(dsl, LayoutDSL)
    assert dsl.sections[0].type == SectionType.hero


def test_qwen_hallucinated_variant_coerced_not_crashed():
    async def fake_chat(**kw):
        return json.dumps({
            "sections": [
                {"type": "hero", "variant": "big_giant_banner"},       # invalid → default
                {"type": "product_grid", "variant": "masonry_grid_4"}, # near-miss → masonry-4col
            ],
            "global_config": {"nav_style": "tabs", "product_card": "mystery"},
        })
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=fake_chat))
    assert dsl.sections[0].variant in _HERO_VALUES


def test_qwen_failure_falls_back():
    async def boom(**kw):
        raise RuntimeError("qwen down")
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=boom))
    assert isinstance(dsl, LayoutDSL)        # never raises
    assert any(s.type == SectionType.product_grid for s in dsl.sections)


def test_qwen_non_json_falls_back():
    async def junk(**kw):
        return "I'm sorry, I cannot help with that."
    dsl = asyncio.run(generate_layout_dsl(_token(), "Haree", "beauty", 6, _chat=junk))
    assert isinstance(dsl, LayoutDSL)

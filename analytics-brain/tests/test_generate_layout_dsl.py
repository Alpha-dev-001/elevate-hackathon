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


def _existing_dsl():
    return LayoutDSL.model_validate({
        "sections": [
            {"type": "hero", "variant": "editorial-stacked"},
            {"type": "product_grid", "variant": "masonry-4col"},
        ],
        "global_config": {"nav_style": "underline-tabs", "product_card": "editorial-horizontal"},
    })


class TestCreativeDirectionAnchoring:
    """Regression coverage for the 'asked for a nav tweak, got a full
    redesign' bug: when editing an EXISTING store, the prompt must anchor
    to the current DSL and instruct Qwen to change only what was asked."""

    def test_current_dsl_included_in_prompt(self):
        captured = {}

        async def fake_chat(**kw):
            captured["messages"] = kw["messages"]
            return json.dumps({
                "sections": [{"type": "hero", "variant": "editorial-stacked"}],
                "global_config": {"nav_style": "pill-nav"},
            })

        asyncio.run(generate_layout_dsl(
            _token(), "Haree", "beauty", 6,
            creative_direction="make the nav text bigger",
            current_dsl=_existing_dsl(),
            _chat=fake_chat,
        ))
        prompt = captured["messages"][0]["content"]
        assert "EDITING it, not" in prompt
        assert "Change ONLY what this request calls for" in prompt
        assert "masonry-4col" in prompt  # the current DSL is actually embedded
        assert "make the nav text bigger" in prompt

    def test_no_current_dsl_uses_fresh_compose_wording(self):
        """First-time generation (onboarding, no store yet) must NOT claim
        there's an existing layout to preserve — nothing to anchor to."""
        captured = {}

        async def fake_chat(**kw):
            captured["messages"] = kw["messages"]
            return json.dumps({
                "sections": [{"type": "hero", "variant": "editorial-stacked"}],
                "global_config": {"nav_style": "pill-nav"},
            })

        asyncio.run(generate_layout_dsl(
            _token(), "Haree", "beauty", 6,
            creative_direction="bold and playful",
            _chat=fake_chat,
        ))
        prompt = captured["messages"][0]["content"]
        assert "EDITING it, not" not in prompt
        assert "bold and playful" in prompt

    def test_no_creative_direction_no_anchoring_text(self):
        """Plain regenerate (no direction at all) shouldn't grow either branch."""
        captured = {}

        async def fake_chat(**kw):
            captured["messages"] = kw["messages"]
            return json.dumps({
                "sections": [{"type": "hero", "variant": "editorial-stacked"}],
                "global_config": {"nav_style": "pill-nav"},
            })

        asyncio.run(generate_layout_dsl(
            _token(), "Haree", "beauty", 6,
            current_dsl=_existing_dsl(),
            _chat=fake_chat,
        ))
        prompt = captured["messages"][0]["content"]
        assert "EDITING it, not" not in prompt
        assert "creative direction" not in prompt.lower()

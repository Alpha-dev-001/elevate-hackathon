from app.services.layout_dsl import fallback_dsl_from_token
from app.models.schemas import (
    BrandToken, BrandColors, BrandTypographyToken, BrandLayoutToken, HeroVariant,
)


def _token(name, style, mood="m", industry="fashion"):
    return BrandToken(
        store_name=name, tagline="t",
        colors=BrandColors(primary="#000", accent="#111", background="#fff", surface="#eee", text="#000", text_muted="#999"),
        typography=BrandTypographyToken(display_font="Syne", body_font="Inter"),
        layout=BrandLayoutToken(style=style, hero_type="split", product_grid="masonry",
                                card_style="borderless", border_radius="8px", spacing="balanced", category_style="pill"),
        mood=mood, industry_hint=industry, brand_voice="v",
    )


def test_deterministic_for_same_token():
    a = fallback_dsl_from_token(_token("Haree", "editorial"))
    b = fallback_dsl_from_token(_token("Haree", "editorial"))
    assert a.model_dump() == b.model_dump()


def test_distinct_across_styles():
    sigs = set()
    for style in ("editorial", "bold-grid", "minimal-dark", "warm-craft"):
        d = fallback_dsl_from_token(_token("Store", style))
        sig = (tuple((s.type.value, s.variant) for s in d.sections),
               d.global_config.nav_style, d.global_config.product_card)
        sigs.add(sig)
    assert len(sigs) == 4   # every base style yields a structurally different store


def test_distinct_across_names_same_style():
    # 40-store distinctness: same style, different brand identity → different store
    sigs = set()
    for i in range(40):
        d = fallback_dsl_from_token(_token(f"brand-{i}", "editorial", mood=f"mood{i % 5}", industry="fashion"))
        sig = (tuple((s.type.value, s.variant) for s in d.sections),
               d.global_config.nav_style, d.global_config.product_card, d.global_config.corner_radius)
        sigs.add(sig)
    assert len(sigs) >= 12   # strong structural variety from seed perturbation


def test_always_valid():
    d = fallback_dsl_from_token(_token("X", "minimal-dark"))
    assert 2 <= len(d.sections) <= 5
    assert any(s.type.value == "product_grid" for s in d.sections)

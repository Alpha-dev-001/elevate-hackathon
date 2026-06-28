from app.models.schemas import (
    LayoutDSL, LayoutSection, LayoutGlobalConfig, BrandToken, MemoryEntry,
    SectionType, HeroVariant, ProductGridVariant, NavStyle, ProductCardVariant,
)


def test_layout_dsl_minimal_valid():
    dsl = LayoutDSL(
        sections=[
            LayoutSection(type=SectionType.hero, variant=HeroVariant.editorial_stacked.value),
            LayoutSection(type=SectionType.product_grid, variant=ProductGridVariant.featured_2col.value),
        ],
        global_config=LayoutGlobalConfig(
            nav_style=NavStyle.underline_tabs,
            product_card=ProductCardVariant.hover_reveal_text,
        ),
        custom_css="",
    )
    assert len(dsl.sections) == 2
    assert dsl.global_config.color_mode == "auto"      # default
    assert dsl.global_config.corner_radius == "md"     # default
    assert dsl.custom_css == ""


def test_brand_token_layout_dsl_optional():
    # layout_dsl defaults to None so existing brand-token rows still validate
    assert "layout_dsl" in BrandToken.model_fields
    assert BrandToken.model_fields["layout_dsl"].default is None


def test_memory_entry_shape():
    e = MemoryEntry(
        action_type="flash_sale",
        trigger="34 views in 28s for face wash",
        outcome="8 orders, $320",
        merchant_behavior="approved",
    )
    assert e.notes == ""
    assert e.timestamp  # auto-populated

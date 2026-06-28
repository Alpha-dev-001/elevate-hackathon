import pytest
from app.services.layout_dsl import normalize_dsl
from app.models.schemas import LayoutDSL, SectionType


def _gc():
    return {"nav_style": "underline-tabs", "product_card": "hover-reveal-text"}


def test_drops_extra_heroes_and_sorts_hero_first():
    out = normalize_dsl({
        "sections": [
            {"type": "product_grid", "variant": "masonry-4col"},
            {"type": "hero", "variant": "editorial-stacked"},
            {"type": "hero", "variant": "split-50-50"},  # extra hero — dropped
        ],
        "global_config": _gc(),
    })
    assert isinstance(out, LayoutDSL)
    assert out.sections[0].type == SectionType.hero
    assert sum(s.type == SectionType.hero for s in out.sections) == 1


def test_injects_product_grid_when_missing():
    out = normalize_dsl({
        "sections": [
            {"type": "hero", "variant": "minimal-wordmark"},
            {"type": "story", "variant": "quote-callout"},
        ],
        "global_config": _gc(),
    })
    assert any(s.type == SectionType.product_grid for s in out.sections)


def test_announcement_bar_floats_to_top():
    out = normalize_dsl({
        "sections": [
            {"type": "hero", "variant": "split-50-50"},
            {"type": "product_grid", "variant": "featured-2col"},
            {"type": "banner", "variant": "announcement-bar"},
        ],
        "global_config": _gc(),
    })
    assert out.sections[0].type == SectionType.banner
    assert out.sections[0].variant == "announcement-bar"


def test_clamps_to_five_sections():
    out = normalize_dsl({
        "sections": [{"type": "product_grid", "variant": "masonry-4col"}] * 9,
        "global_config": _gc(),
    })
    assert 2 <= len(out.sections) <= 5


def test_empty_sections_still_yields_valid_dsl():
    out = normalize_dsl({"sections": [], "global_config": _gc()})
    assert len(out.sections) >= 2
    assert any(s.type == SectionType.product_grid for s in out.sections)


def test_no_two_banners_adjacent():
    out = normalize_dsl({
        "sections": [
            {"type": "banner", "variant": "static-strip"},
            {"type": "banner", "variant": "scroll-ticker"},
            {"type": "product_grid", "variant": "masonry-4col"},
        ],
        "global_config": _gc(),
    })
    types = [s.type for s in out.sections]
    for a, b in zip(types, types[1:]):
        assert not (a == SectionType.banner and b == SectionType.banner)

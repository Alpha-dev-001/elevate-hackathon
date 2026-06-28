from app.models.schemas import SectionType
from app.services.layout_dsl import coerce_variant, VALID_VARIANTS, DEFAULT_VARIANT


def test_exact_variant_passes_through():
    assert coerce_variant(SectionType.hero, "editorial-stacked") == "editorial-stacked"


def test_near_miss_underscore_coerced():
    assert coerce_variant(SectionType.hero, "editorial_stacked") == "editorial-stacked"


def test_synonym_coerced():
    # 'full bleed' → full-bleed-image
    assert coerce_variant(SectionType.hero, "full bleed") == "full-bleed-image"


def test_wrong_type_variant_falls_back_to_type_default():
    # a product-grid variant requested on a hero section → hero default, never cross-type
    out = coerce_variant(SectionType.hero, "masonry-4col")
    assert out in VALID_VARIANTS[SectionType.hero]
    assert out == DEFAULT_VARIANT[SectionType.hero]


def test_garbage_falls_back_to_type_default():
    assert coerce_variant(SectionType.banner, "🔥unknown🔥") == DEFAULT_VARIANT[SectionType.banner]

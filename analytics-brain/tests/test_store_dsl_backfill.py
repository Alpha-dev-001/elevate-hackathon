"""Unit test for the public-store layout_dsl threading + backfill mechanism.
Verifiable without the live stack; the live contract is in test_store_dsl_live.py."""
from app.models.schemas import (
    BrandToken, BrandColors, BrandTypographyToken, BrandLayoutToken,
)
from app.services.layout_dsl import fallback_dsl_from_token


def _token_dict(with_dsl: bool):
    bt = BrandToken(
        store_name="Haree", tagline="t",
        colors=BrandColors(primary="#000", accent="#6EE7B7", background="#0A0A0B", surface="#111", text="#fff", text_muted="#999"),
        typography=BrandTypographyToken(display_font="Syne", body_font="Inter"),
        layout=BrandLayoutToken(style="editorial", hero_type="split", product_grid="masonry",
                                card_style="borderless", border_radius="8px", spacing="balanced", category_style="pill"),
        mood="refined", industry_hint="beauty", brand_voice="quiet",
    )
    if with_dsl:
        bt.layout_dsl = fallback_dsl_from_token(bt)
    return bt.model_dump()


def test_layout_dsl_survives_round_trip():
    d = _token_dict(with_dsl=True)
    bt = BrandToken.model_validate(d)
    assert bt.layout_dsl is not None
    assert 2 <= len(bt.layout_dsl.sections) <= 5


def test_missing_layout_dsl_is_backfilled():
    # Simulate a pre-Sprint-3 brand_tokens row with no layout_dsl key.
    d = _token_dict(with_dsl=False)
    d.pop("layout_dsl", None)
    bt = BrandToken.model_validate(d)
    assert bt.layout_dsl is None                 # validates fine without the key
    bt.layout_dsl = fallback_dsl_from_token(bt)  # the route's backfill step
    assert bt.layout_dsl is not None
    assert any(s.type.value == "product_grid" for s in bt.layout_dsl.sections)

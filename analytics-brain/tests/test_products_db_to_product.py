"""Tests for db_to_product's field mapping — pure function, no I/O."""
from app.models.db_models import ProductDB
from app.services.products import db_to_product


def _row(**overrides):
    defaults = dict(
        id="p1", merchant_id="m1", name="Slides", price=40.0, cost_price=20.0,
        baseline_price=40.0,
        stock=5, category="footwear", image_urls=["https://x/a.jpg"],
        is_active=True, qwen_generated_description=True,
        is_featured=False, featured_label=None,
    )
    defaults.update(overrides)
    return ProductDB(**defaults)


class TestDbToProductFeaturedFields:
    def test_defaults_not_featured(self):
        product = db_to_product(_row())
        assert product.is_featured is False
        assert product.featured_label is None

    def test_maps_featured_state(self):
        product = db_to_product(_row(is_featured=True, featured_label="New Arrival"))
        assert product.is_featured is True
        assert product.featured_label == "New Arrival"


def test_db_to_product_includes_baseline_price():
    # baseline_price deliberately differs from price here to prove
    # db_to_product passes it through as its own field, not a price alias.
    product = db_to_product(_row(price=20.0, cost_price=10.0, baseline_price=18.0))
    assert product.baseline_price == 18.0


def test_db_to_product_crashes_if_is_featured_omitted_pre_flush():
    """Regression guard for the vision_batch crash: ProductDB.is_featured
    has a DB-side default (Boolean, default=False), but that default is only
    materialized by SQLAlchemy at flush/INSERT time. Calling db_to_product()
    on a ProductDB row that was just constructed and db.add()-ed, but never
    flushed, sees is_featured=None and blows up Product's bool validation.
    vision_batch's router now passes is_featured=False explicitly — this
    test pins down WHY that's required so it can't quietly regress."""
    import pytest
    row = ProductDB(
        id="p1", merchant_id="m1", name="Slides", price=40.0, cost_price=20.0,
        baseline_price=40.0, stock=5, category="footwear",
        image_urls=["https://x/a.jpg"], is_active=False,
        qwen_generated_description=True,
        # is_featured deliberately omitted — never flushed, so SQLAlchemy's
        # column default hasn't run yet.
    )
    with pytest.raises(Exception):  # pydantic_core.ValidationError
        db_to_product(row)

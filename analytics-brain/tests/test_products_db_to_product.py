"""Tests for db_to_product's field mapping — pure function, no I/O."""
from app.models.db_models import ProductDB
from app.services.products import db_to_product


def _row(**overrides):
    defaults = dict(
        id="p1", merchant_id="m1", name="Slides", price=40.0, cost_price=20.0,
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

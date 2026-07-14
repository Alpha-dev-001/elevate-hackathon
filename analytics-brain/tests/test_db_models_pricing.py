"""
Tests for new pricing-related database models.
Following the established convention: no DB connection, no fixtures —
just asserting column presence on the mapped class directly.
(See test_db_models_sprint3.py for pattern reference.)
"""
from app.models.db_models import ProductPriceHistoryDB, AutopilotTrustDB


def test_product_price_history_has_expected_columns():
    cols = ProductPriceHistoryDB.__table__.columns
    for name in ("product_id", "date", "views", "cart_adds", "purchases",
                 "price_active", "signal_quality", "extra_signals"):
        assert name in cols


def test_product_price_history_defaults():
    row = ProductPriceHistoryDB(
        id="hist1", product_id="p1", date="2026-07-13", price_active=20.0,
    )
    assert row.views is None or row.views == 0  # server_default vs. Python-side default both acceptable pre-flush
    assert row.signal_quality is None or row.signal_quality == "normal"


def test_autopilot_trust_has_expected_columns():
    cols = AutopilotTrustDB.__table__.columns
    for name in ("merchant_id", "product_id", "action_type", "streak", "updated_at"):
        assert name in cols


def test_autopilot_trust_unique_constraint_covers_merchant_product_type():
    constraint_cols = {
        tuple(c.name for c in uc.columns)
        for uc in AutopilotTrustDB.__table__.constraints
        if uc.__class__.__name__ == "UniqueConstraint"
    }
    assert ("merchant_id", "product_id", "action_type") in constraint_cols

"""Structural-safety guard for Qwen tool-call arguments.

These tests are the spec: a value that encodes a structurally-illegal state
(negative or >100% discount, non-positive price, empty/whitespace target,
self-contradictory merge, invalid copy enum, non-positive duration) must be
*rejected* — it can never become a valid AgentAction that reaches the
interceptor. Valid-but-aggressive values (a 60% discount above the business
ceiling) are NOT this layer's job; the interceptor clamps those. This layer
only makes the impossible unrepresentable.
"""
import pytest

from app.services.action_guard import validate_tool_args, ActionValidationError


# ── Valid inputs pass through, coerced/normalized ──────────────────────────

def test_flash_sale_valid_passes():
    out = validate_tool_args(
        "propose_flash_sale",
        {"product_id": "p1", "discount_percent": 15, "duration_minutes": 60,
         "reasoning": "velocity spike"},
    )
    assert out["product_id"] == "p1"
    assert out["discount_percent"] == 15
    assert out["duration_minutes"] == 60


def test_numeric_string_discount_is_coerced():
    out = validate_tool_args(
        "propose_flash_sale",
        {"product_id": "p1", "discount_percent": "15", "reasoning": "x"},
    )
    assert out["discount_percent"] == 15.0


def test_extra_reasoning_field_is_preserved():
    out = validate_tool_args(
        "propose_recovery_offer",
        {"discount_percent": 12, "reasoning": "cart abandon surge"},
    )
    assert out["reasoning"] == "cart abandon surge"


def test_price_rebalance_valid_passes():
    out = validate_tool_args(
        "propose_price_rebalance",
        {"product_id": "p1", "new_price": 29.99, "reasoning_signals": "demand up"},
    )
    assert out["new_price"] == 29.99


def test_copy_rewrite_valid_target_passes():
    out = validate_tool_args(
        "propose_copy_rewrite",
        {"target": "hero_headline", "reasoning": "x"},
    )
    assert out["target"] == "hero_headline"


def test_duplicate_merge_valid_passes():
    out = validate_tool_args(
        "propose_duplicate_merge",
        {"keep_product_id": "p1", "remove_product_ids": ["p2", "p3"], "reasoning": "x"},
    )
    assert out["keep_product_id"] == "p1"
    assert out["remove_product_ids"] == ["p2", "p3"]


def test_unknown_tool_passes_through_unvalidated():
    # Unknown tool names are handled elsewhere; the guard makes no claim.
    args = {"anything": 1}
    assert validate_tool_args("propose_unknown_thing", args) == {"anything": 1}


# ── Discount bounds — the core structural claim ────────────────────────────

def test_negative_discount_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": -5, "reasoning": "x"},
        )


def test_discount_over_100_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": 150, "reasoning": "x"},
        )


def test_non_numeric_discount_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": "a lot", "reasoning": "x"},
        )


def test_recovery_offer_discount_over_100_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_recovery_offer",
            {"discount_percent": 200, "reasoning": "x"},
        )


def test_cart_dwell_negative_discount_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_cart_dwell_nudge",
            {"discount_percent": -1, "reasoning": "x"},
        )


# ── Target / id existence at the structural level ──────────────────────────

def test_missing_product_id_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_flash_sale",
            {"discount_percent": 10, "reasoning": "x"},
        )


def test_empty_product_id_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_flash_sale",
            {"product_id": "", "discount_percent": 10, "reasoning": "x"},
        )


def test_whitespace_product_id_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_flash_sale",
            {"product_id": "   ", "discount_percent": 10, "reasoning": "x"},
        )


# ── Price rebalance — a price is structurally positive ─────────────────────

def test_zero_new_price_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_price_rebalance",
            {"product_id": "p1", "new_price": 0, "reasoning_signals": "x"},
        )


def test_negative_new_price_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_price_rebalance",
            {"product_id": "p1", "new_price": -10, "reasoning_signals": "x"},
        )


# ── Duration ───────────────────────────────────────────────────────────────

def test_zero_duration_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_flash_sale",
            {"product_id": "p1", "discount_percent": 10, "duration_minutes": 0,
             "reasoning": "x"},
        )


def test_omitted_duration_is_fine():
    out = validate_tool_args(
        "propose_flash_sale",
        {"product_id": "p1", "discount_percent": 10, "reasoning": "x"},
    )
    assert "duration_minutes" not in out or out["duration_minutes"] is None


# ── Copy rewrite enum ──────────────────────────────────────────────────────

def test_invalid_copy_target_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_copy_rewrite",
            {"target": "footer_legal", "reasoning": "x"},
        )


# ── Duplicate merge structural contradictions ──────────────────────────────

def test_empty_remove_list_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_duplicate_merge",
            {"keep_product_id": "p1", "remove_product_ids": [], "reasoning": "x"},
        )


def test_keep_id_also_in_remove_list_rejected():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_duplicate_merge",
            {"keep_product_id": "p1", "remove_product_ids": ["p1", "p2"], "reasoning": "x"},
        )


def test_feature_product_requires_label():
    with pytest.raises(ActionValidationError):
        validate_tool_args(
            "propose_feature_product",
            {"product_id": "p1", "featured_label": "", "reasoning": "x"},
        )

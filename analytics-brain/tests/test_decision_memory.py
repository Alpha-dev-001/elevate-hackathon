from app.services.decision_engine import compose_decision_prompt


def test_prompt_includes_memory_when_present():
    prompt = compose_decision_prompt(
        store_name="Haree", mood="refined", brand_voice="quiet",
        brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
        anomaly_description="34 views in 28s for face wash",
        memory_context="What I know about this store:\n[2026-06-27] flash_sale: spike → 8 orders, $320 (merchant: approved)",
    )
    assert "8 orders, $320" in prompt
    assert "tools" in prompt.lower()           # tool-calling prompt references available tools
    assert "Haree" in prompt


def test_prompt_omits_memory_block_when_empty():
    prompt = compose_decision_prompt(
        store_name="Haree", mood="refined", brand_voice="quiet",
        brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
        anomaly_description="34 views in 28s",
        memory_context="",
    )
    assert "What I know about this store" not in prompt
    assert "tools" in prompt.lower()


def test_prompt_states_the_real_discount_ceiling_not_a_default():
    """Regression for Notice.md #10: Qwen was guessing a discount blind and
    converging on a generic 10% (see BENCHMARKS.md's "subconscious vs.
    without one") because the prompt never told it the merchant's actual
    max_discount_percent. It must be stated explicitly and reflect the real
    per-merchant value, not a hardcoded number."""
    prompt = compose_decision_prompt(
        store_name="Haree", mood="refined", brand_voice="quiet",
        brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
        anomaly_description="34 views in 28s",
        max_discount_percent=65.0,
    )
    assert "65%" in prompt
    assert "10%" not in prompt

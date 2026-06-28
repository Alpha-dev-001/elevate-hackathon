from app.services.decision_engine import compose_decision_prompt


def test_prompt_includes_memory_when_present():
    prompt = compose_decision_prompt(
        store_name="Haree", mood="refined", brand_voice="quiet",
        brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
        anomaly_description="34 views in 28s for face wash",
        memory_context="What I know about this store:\n[2026-06-27] flash_sale: spike → 8 orders, $320 (merchant: approved)",
    )
    assert "8 orders, $320" in prompt
    assert "json" in prompt.lower()           # DashScope json_object requires the literal word
    assert "Haree" in prompt


def test_prompt_omits_memory_block_when_empty():
    prompt = compose_decision_prompt(
        store_name="Haree", mood="refined", brand_voice="quiet",
        brand_rules_summary="protect accent", products_summary="Face Wash ($24, stock: 50)",
        anomaly_description="34 views in 28s",
        memory_context="",
    )
    assert "What I know about this store" not in prompt
    assert "json" in prompt.lower()

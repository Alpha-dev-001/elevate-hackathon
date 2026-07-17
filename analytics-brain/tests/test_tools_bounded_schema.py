"""The tool JSON schemas themselves carry numeric bounds, so Qwen is
constrained at generation time — not only caught afterward by the guard.
A discount property with no min/max lets the model emit 500 or -20 as
'valid' structured output; bounding the schema closes that at the source.
"""
from app.services.tools import DECISION_TOOLS


def _props(tool):
    return tool["function"]["parameters"]["properties"]


def test_every_discount_percent_is_bounded_0_to_100():
    seen = 0
    for tool in DECISION_TOOLS:
        props = _props(tool)
        if "discount_percent" in props:
            seen += 1
            dp = props["discount_percent"]
            assert dp.get("minimum") == 0, f"{tool['function']['name']} discount has no minimum"
            assert dp.get("maximum") == 100, f"{tool['function']['name']} discount has no maximum"
    assert seen >= 4  # flash_sale, scarcity, recovery, cart_dwell all carry one


def test_new_price_is_strictly_positive_in_schema():
    tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_price_rebalance")
    np = _props(tool)["new_price"]
    assert np.get("exclusiveMinimum") == 0


def test_duration_minutes_is_strictly_positive_in_schema():
    tool = next(t for t in DECISION_TOOLS if t["function"]["name"] == "propose_flash_sale")
    dm = _props(tool)["duration_minutes"]
    assert dm.get("exclusiveMinimum") == 0

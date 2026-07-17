"""extract_reasoning — a real production gap found live: reasoning was empty
for ~95% of logged decisions (52/55 rows in the Xair store) because it was
sourced from message.content, which tool-calling Qwen reliably omits once it
decides to call a function. DECISION_TOOLS now requires a structured
"reasoning" argument per tool instead; this is the read-side of that fix."""
from app.services.decision_engine import extract_reasoning


class TestExtractReasoning:
    def test_prefers_structured_reasoning_arg(self):
        tool_args = {"discount_percent": 10, "reasoning": "12 abandons in 30s, avg cart $40"}
        message = {"content": ""}
        assert extract_reasoning(tool_args, message) == "12 abandons in 30s, avg cart $40"

    def test_falls_back_to_reasoning_signals_for_price_rebalance(self):
        tool_args = {"new_price": 30.0, "reasoning_signals": "purchases up 40% at current price"}
        message = {"content": ""}
        assert extract_reasoning(tool_args, message) == "purchases up 40% at current price"

    def test_falls_back_to_message_content_when_neither_present(self):
        tool_args = {"discount_percent": 10}
        message = {"content": "Legacy freeform reasoning from an older schema"}
        assert extract_reasoning(tool_args, message) == "Legacy freeform reasoning from an older schema"

    def test_reasoning_arg_wins_over_message_content(self):
        tool_args = {"reasoning": "structured wins"}
        message = {"content": "freeform loses"}
        assert extract_reasoning(tool_args, message) == "structured wins"

    def test_empty_everywhere_returns_empty_string(self):
        assert extract_reasoning({}, {}) == ""

    def test_none_message_content_does_not_crash(self):
        assert extract_reasoning({}, {"content": None}) == ""

    def test_truncates_to_1000_chars(self):
        tool_args = {"reasoning": "x" * 2000}
        assert len(extract_reasoning(tool_args, {})) == 1000

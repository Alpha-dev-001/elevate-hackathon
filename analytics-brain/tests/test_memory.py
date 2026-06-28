from datetime import datetime, timezone
from app.models.schemas import MemoryEntry
from app.services.memory import build_memory_context


def _e(action, outcome, behavior="approved"):
    return MemoryEntry(timestamp=datetime(2026, 6, 27, tzinfo=timezone.utc),
                       action_type=action, trigger="t", outcome=outcome, merchant_behavior=behavior)


def test_empty_returns_empty_string():
    assert build_memory_context([]) == ""


def test_includes_action_outcome_and_behavior():
    ctx = build_memory_context([_e("flash_sale", "8 orders, $320")])
    assert "flash_sale" in ctx and "$320" in ctx and "approved" in ctx
    assert ctx.startswith("What I know about this store:")


def test_caps_to_limit():
    entries = [_e("flash_sale", f"{i} orders") for i in range(20)]
    ctx = build_memory_context(entries, limit=8)
    assert ctx.count("\n") <= 8  # header + 8 lines max

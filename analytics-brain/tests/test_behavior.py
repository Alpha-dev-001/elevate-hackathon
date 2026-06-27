"""Test behavior event ingestion — no Qwen calls, no WS, just Redis writes."""
import pytest
import httpx

BASE = "http://localhost:9000"


def test_behavior_event_ingest():
    resp = httpx.post(
        f"{BASE}/api/behavior/event/haree",
        json={
            "event_type": "view",
            "product_id": "test-product",
            "session_id": "test-session-001",
            "timestamp": 1751000000.0,
        },
        timeout=5,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True


def test_get_pending_actions_empty():
    resp = httpx.get(f"{BASE}/api/agent/actions/haree/pending", timeout=5)
    assert resp.status_code == 200, resp.text
    assert "actions" in resp.json()


def test_dashboard():
    resp = httpx.get(f"{BASE}/api/dashboard/haree", timeout=5)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "total_gmv" in data
    assert "actions" in data

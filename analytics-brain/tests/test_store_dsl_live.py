"""Requires docker compose up + a published store 'haree' with a brand_token."""
import httpx

BASE = "http://localhost:9000"


def test_public_store_includes_layout_dsl():
    r = httpx.get(f"{BASE}/api/store/haree", timeout=10)
    assert r.status_code == 200, r.text
    bt = r.json().get("brand_token")
    assert bt is not None, "haree must have a brand_token"
    dsl = bt.get("layout_dsl")
    assert dsl is not None, "layout_dsl must be threaded into the public payload"
    assert 2 <= len(dsl["sections"]) <= 5
    assert "global_config" in dsl

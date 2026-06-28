"""Requires docker compose up + an authenticated merchant whose slug is 'haree'.
Auth cookie/token handling depends on the test harness; this documents the
PUT/POST contract for the DSL endpoints.
"""
import httpx

BASE = "http://localhost:9000"


def _auth_client() -> httpx.Client:
    # Login as the demo merchant. Adjust creds to your seeded demo account.
    c = httpx.Client(base_url=BASE, timeout=15)
    c.post("/auth/login", json={"email": "demo@haree.test", "password": "password123"})
    return c


def test_put_dsl_normalizes_and_persists():
    c = _auth_client()
    # A deliberately 1-section DSL must come back normalized to >=2 sections.
    body = {
        "sections": [{"type": "product_grid", "variant": "masonry-4col", "props": {}}],
        "global_config": {"nav_style": "pill-nav", "product_card": "polaroid-card"},
        "custom_css": "",
    }
    r = c.put("/api/brand/dsl/haree", json=body)
    assert r.status_code == 200, r.text
    dsl = r.json()
    assert 2 <= len(dsl["sections"]) <= 5

    # And the public store reflects the saved DSL.
    s = c.get("/api/store/haree")
    assert s.status_code == 200
    assert s.json()["brand_token"]["layout_dsl"] is not None

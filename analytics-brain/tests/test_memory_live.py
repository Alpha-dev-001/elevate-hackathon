"""Requires docker compose up + an authenticated merchant whose slug is 'haree'.
Documents the memory read contract (auth handling depends on the harness)."""
import httpx

BASE = "http://localhost:9000"


def test_memory_endpoint_shape():
    c = httpx.Client(base_url=BASE, timeout=15)
    c.post("/auth/login", json={"email": "demo@haree.test", "password": "password123"})
    r = c.get("/merchant/memory/haree")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "entries" in body and isinstance(body["entries"], list)
    assert "count" in body and isinstance(body["count"], int)

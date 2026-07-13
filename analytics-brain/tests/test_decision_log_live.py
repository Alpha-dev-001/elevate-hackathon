"""Requires docker compose up + a running server on port 9000. First
automated coverage for GET /merchant/decisions — same httpx pytest-function
convention as test_memory_live.py / test_deduplicate_live.py."""
import uuid
import httpx

BASE = "http://127.0.0.1:9000"


def test_decisions_endpoint_shape_and_pagination():
    email = f"decisionlog_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Decision Log Test Co", "password": "a-strong-password",
            "category": "fashion", "description": "Test store for decision log coverage",
        })
        assert r.status_code == 201, r.text

        r = c.get("/merchant/decisions")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "decisions" in body and isinstance(body["decisions"], list)
        assert "total" in body and isinstance(body["total"], int)
        assert body["total"] == 0  # brand-new store, no actions yet

        r = c.get("/merchant/decisions?limit=5&offset=0")
        assert r.status_code == 200, r.text
        assert len(r.json()["decisions"]) <= 5

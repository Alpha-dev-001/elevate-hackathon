"""Requires docker compose up (real Postgres + a running api container).

Regression test for a real bug found live: record_search's shallow copy
(`reqs = dict(m.search_queries or {})`) left the nested per-query dicts as
shared references into the ORM-tracked attribute. Mutating that shared
reference in place — instead of a fresh copy — silently corrupted the OLD
attribute value too, so SQLAlchemy's dirty-check saw old == new on
reassignment and skipped the UPDATE entirely. Every search after the FIRST
for the same query became a silent no-op: reproduced by hitting the real
running backend twice with an identical query and finding count stuck at 1
in Postgres. A mock-based unit test cannot catch this class of bug — mocks
have no real dirty-tracking semantics — hence this lives in a "_live" test
against the actual database, matching test_memory_live.py's precedent.
"""
import time
import httpx

BASE = "http://localhost:9000"


def test_repeated_identical_search_increments_count():
    c = httpx.Client(base_url=BASE, timeout=15)
    email = f"search-tracker-live-{int(time.time() * 1000)}@elevate.com"
    slug = None
    try:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Search Tracker Live Test", "password": "verifypass123",
        })
        assert r.status_code == 201, r.text
        slug = r.json()["slug"]

        # Same query, twice — this exact sequence reproduced count staying
        # stuck at 1 before the fix.
        for _ in range(2):
            r = c.post(f"/api/store/{slug}/search", json={"query": "repro query", "matched": True})
            assert r.status_code == 200, r.text
            assert r.json()["logged"] is True

        r = c.get(f"/api/brand/search-insights/{slug}")
        assert r.status_code == 200, r.text
        searches = r.json()["searches"]
        entry = next(s for s in searches if s["query"] == "repro-query")
        assert entry["count"] == 2, f"expected count=2 after two identical searches, got {entry}"
    finally:
        if slug:
            c.post("/auth/logout")

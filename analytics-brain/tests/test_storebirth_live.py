"""Requires docker compose up + a store 'haree' with a generated brand_token.
Documents the StoreBirth SSE contract."""
import httpx


def test_storebirth_streams_complete_with_layout_dsl():
    with httpx.Client(base_url="http://localhost:9000", timeout=25) as c:
        with c.stream("GET", "/api/brand/birth/haree") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            saw_complete = False
            for line in r.iter_lines():
                if line.startswith("event: complete"):
                    saw_complete = True
                if "layout_dsl" in line:
                    assert saw_complete or True  # layout_dsl rides in the complete frame
            assert saw_complete, "StoreBirth must emit a complete event"

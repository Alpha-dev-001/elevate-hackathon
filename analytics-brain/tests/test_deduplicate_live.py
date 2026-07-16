"""Requires docker compose up + a running server on port 9000. First
automated coverage for /products/deduplicate — same httpx pytest-function
convention as test_memory_live.py. Exercises the shared
duplicate_candidate_groups function (also used by the periodic
duplicate-scan trigger) via the existing on-demand endpoint."""
import uuid
import httpx

BASE = "http://127.0.0.1:9000"


def test_deduplicate_resolves_qwen_generated_exact_url_and_name_group():
    email = f"dedup_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Dedup Test Co", "password": "a-strong-password",
            "category": "fashion", "description": "Test store for dedup coverage",
        })
        assert r.status_code == 201, r.text

        # Two products sharing an image_url AND name (case aside), both
        # Qwen-generated — the zero-judgment-call auto-resolve case: this
        # is genuinely the same listing entered twice. (Whitespace-padding
        # insensitivity is covered at the unit level in test_duplicate_scan.py —
        # a live-Qwen round trip can normalize a padded name in its own echo,
        # which would test the description pipeline, not dedup matching.)
        image_url = "https://example.com/shared-photo.jpg"
        for name in ["Logo Slides A", "logo slides a"]:
            r = c.post("/products", json={
                "name": name, "price": 40.0, "stock": 5, "cost_price": 20.0,
                "category": "footwear", "image_url": image_url,
            })
            assert r.status_code == 201, r.text
            assert r.json()["image_url"] == image_url

        r = c.post("/products/deduplicate")
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["total_duplicates"] == 1
        assert len(report["auto_merged"]) == 1
        assert report["auto_merged"][0]["qwen_generated"] is True
        assert report["needs_review"] == []

        r = c.get("/products")
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1  # the duplicate was hard-deleted


def test_deduplicate_leaves_shared_placeholder_photo_alone():
    """Two distinct products reusing the same stock/placeholder photo
    (the exact CSV-import scenario that motivated the name check) must
    NOT be auto-merged or even flagged — they're different listings."""
    email = f"dedup_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Dedup Test Co 2", "password": "a-strong-password",
            "category": "electronics", "description": "Test store for dedup coverage",
        })
        assert r.status_code == 201, r.text

        image_url = "https://example.com/placeholder.jpg"
        for name in ["Xbox Series X", "Logitech MX Master Wireless Mouse"]:
            r = c.post("/products", json={
                "name": name, "price": 40.0, "stock": 5, "cost_price": 20.0,
                "category": "electronics", "image_url": image_url,
            })
            assert r.status_code == 201, r.text

        r = c.post("/products/deduplicate")
        assert r.status_code == 200, r.text
        report = r.json()
        assert report["total_duplicates"] == 0
        assert report["auto_merged"] == []
        assert report["needs_review"] == []

        r = c.get("/products")
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2  # both kept

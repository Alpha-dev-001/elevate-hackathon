"""
Live products integration test — single add + CSV batch + list, against the
running server (port 9000) with real Postgres + Redis + Qwen descriptions.
No brand is generated (fast) — description generation falls back to the neutral
voice, exercising the real batched qwen-max call.

Run the server first:  uvicorn app.main:app --port 9000
"""
import uuid
import httpx

BASE = "http://127.0.0.1:9000"


def main() -> int:
    email = f"prod_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=90) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Gear Co", "password": "a-strong-password",
            "category": "sports", "description": "Trail and outdoor gear",
        })
        assert r.status_code == 201, r.text
        print("1. signed up")

        # 1. single add — carries cost_price, gets a real description
        r = c.post("/products", json={
            "name": "Trail Runner 2.0", "price": 129.0, "stock": 25,
            "cost_price": 60.0, "category": "footwear",
            "image_url": "https://example.com/shoe.jpg",
        })
        assert r.status_code == 201, r.text
        p = r.json()
        assert p["description"] and len(p["description"]) > 10, p
        assert p["cost_price"] == 60.0 and p["price"] == 129.0
        assert p["image_url"] == "https://example.com/shoe.jpg"
        print(f"2. single add 201 — desc: {p['description'][:80]}")

        # 2. CSV batch — no cost_price; ONE qwen call for all three
        rows = [
            {"name": "Summit Pack 40L", "price": 180, "stock": 10, "category": "bags"},
            {"name": "Cloud Tent 2P", "price": 240, "stock": 6, "category": "shelter"},
            {"name": "Trail Flask 750ml", "price": 28, "stock": 50, "category": "hydration"},
        ]
        r = c.post("/products/batch", json={"products": rows})
        assert r.status_code == 201, r.text
        batch = r.json()
        assert len(batch) == 3, batch
        for b in batch:
            assert b["description"] and len(b["description"]) > 10, b
            # CSV-derived cost price = 60% of price
            assert abs(b["cost_price"] - round(b["price"] * 0.6, 2)) < 0.01, b
        print(f"3. batch add 201 — {len(batch)} products, all described")
        for b in batch:
            print(f"   {b['name']}: {b['description'][:70]}")

        # 3. list returns all four
        r = c.get("/products")
        assert r.status_code == 200, r.text
        assert len(r.json()) == 4, r.json()
        print(f"4. list -> {len(r.json())} products")

        # 4. validation: bad price rejected pre-DB
        r = c.post("/products", json={"name": "X", "price": -5, "stock": 1, "cost_price": 1})
        assert r.status_code == 422, r.text
        print("5. negative price -> 422")

        # 5. auth required
        r = httpx.get(f"{BASE}/products", timeout=10)
        assert r.status_code == 401, r.text
        print("6. unauthenticated list -> 401")

    print("ALL PRODUCTS LIVE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

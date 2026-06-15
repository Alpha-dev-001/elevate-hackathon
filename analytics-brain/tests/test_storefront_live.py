"""
Live storefront test — provisions a real store (brand + products + publish) and
checks the public payload at GET /api/store/{slug}. Confirms cost_price never
leaks to the customer-facing endpoint.

Run the server first:  uvicorn app.main:app --port 9000
"""
import time
import uuid
import httpx

BASE = "http://127.0.0.1:9000"
LOGO = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"


def main() -> int:
    email = f"store_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=120) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Lumen Home", "password": "a-strong-password",
            "category": "home", "description": "Warm minimal homeware",
        })
        assert r.status_code == 201, r.text
        slug = r.json()["slug"]
        print(f"1. signed up (slug={slug})")

        # public store 404 before publish
        r = c.get(f"/api/store/{slug}")
        assert r.status_code == 404, r.text
        print("2. public store -> 404 before publish")

        # generate brand (poll the durable GET instead of WS)
        r = c.post("/onboarding/start", json={"logo_oss_url": LOGO})
        assert r.status_code == 202, r.text
        print("3. brand pipeline started, polling…")
        t0 = time.time()
        while time.time() - t0 < 100:
            r = c.get("/onboarding/brand")
            if r.status_code == 200:
                break
            time.sleep(3)
        assert r.status_code == 200, f"brand never ready: {r.text}"
        print(f"4. brand ready in {time.time()-t0:.0f}s")

        # add products (single + batch)
        r = c.post("/products", json={"name": "Linen Throw", "price": 68, "stock": 12, "cost_price": 30, "category": "textiles"})
        assert r.status_code == 201, r.text
        r = c.post("/products/batch", json={"products": [
            {"name": "Oak Board", "price": 42, "stock": 0, "category": "kitchen"},
            {"name": "Clay Mug", "price": 24, "stock": 30, "category": "ceramics"},
        ]})
        assert r.status_code == 201, r.text
        print("5. added 3 products (one out of stock)")

        # publish
        r = c.post("/onboarding/publish")
        assert r.status_code == 200, r.text
        print("6. published")

        # public store payload
        r = c.get(f"/api/store/{slug}")
        assert r.status_code == 200, r.text
        store = r.json()
        assert store["store_name"] == "Lumen Home"
        assert store["palette"]["accent"].startswith("#")
        assert store["typography"]["display_font"]
        assert "<svg" in store["icons"]["logo_mark"]
        assert len(store["products"]) == 3, store["products"]
        # cost_price MUST NOT leak
        for p in store["products"]:
            assert "cost_price" not in p, f"cost_price leaked! {p}"
            assert "available" in p
        oak = next(p for p in store["products"] if p["name"] == "Oak Board")
        assert oak["available"] is False, "out-of-stock product should be unavailable"
        throw = next(p for p in store["products"] if p["name"] == "Linen Throw")
        assert throw["available"] is True and throw["description"]
        print(f"7. public payload OK — {len(store['products'])} products, no cost leak, availability correct")
        print(f"   tagline: {store['tagline']}")

        # unknown slug -> 404
        r = c.get("/api/store/no-such-store-xyz")
        assert r.status_code == 404
        print("8. unknown slug -> 404")

    print("ALL STOREFRONT LIVE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

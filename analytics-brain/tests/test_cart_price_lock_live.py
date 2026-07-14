"""
Cart price-lock live integration test — proves CartItem.unit_price really is
a snapshot that survives a later Product.price change, against the running
server (port 9000) with real Postgres + Redis + Qwen brand generation. This
is the guarantee the whole dynamic-baseline-pricing design leans on instead
of rebuilding it (schemas.py's CartItem.unit_price docstring: "SNAPSHOT — the
effective price when added; never re-derived").

Run the server first:  uvicorn app.main:app --port 9000
"""
import time
import uuid
import httpx

BASE = "http://127.0.0.1:9000"
LOGO = "https://help-static-aliyun-doc.aliyuncs.com/file-manage-files/zh-CN/20241022/emyrja/dog_and_girl.jpeg"


def main() -> int:
    email = f"cartlock_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=120) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Lock Co", "password": "a-strong-password",
            "category": "other", "description": "Cart price-lock test store",
        })
        assert r.status_code == 201, r.text
        slug = r.json()["slug"]
        print(f"1. signed up (slug={slug})")

        r = c.post("/onboarding/start", json={"logo_oss_url": LOGO})
        assert r.status_code == 202, r.text
        print("2. brand pipeline started, polling…")
        t0 = time.time()
        while time.time() - t0 < 100:
            r = c.get("/onboarding/brand")
            if r.status_code == 200:
                break
            time.sleep(3)
        assert r.status_code == 200, f"brand never ready: {r.text}"
        print(f"3. brand ready in {time.time()-t0:.0f}s")

        r = c.post("/products", json={
            "name": "Lockable Widget", "price": 50.0, "stock": 10,
            "cost_price": 20.0, "category": "general",
        })
        assert r.status_code == 201, r.text
        product_id = r.json()["id"]
        print("4. product created at $50.00")

        r = c.post("/onboarding/publish")
        assert r.status_code == 200, r.text
        print("5. published")

        session_id = f"sess_{uuid.uuid4().hex[:16]}"
        r = c.post(f"/api/store/{slug}/cart/items", json={
            "session_id": session_id, "product_id": product_id, "qty": 1,
        })
        assert r.status_code == 200, r.text
        cart = r.json()
        assert cart["items"][0]["unit_price"] == 50.0, cart
        print("6. added to cart at $50.00")

        r = c.patch(f"/products/{product_id}", json={"price": 35.0})
        assert r.status_code == 200, r.text
        print("7. merchant dropped live price to $35.00")

        r = c.get(f"/api/store/{slug}/cart", params={"session_id": session_id})
        assert r.status_code == 200, r.text
        cart_after = r.json()
        assert cart_after["items"][0]["unit_price"] == 50.0, (
            f"PRICE LOCK BROKEN: cart line re-derived to "
            f"{cart_after['items'][0]['unit_price']} instead of staying at 50.0"
        )
        print("8. cart still shows $50.00 after the price drop — snapshot held")

    print("\nAll cart price-lock checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

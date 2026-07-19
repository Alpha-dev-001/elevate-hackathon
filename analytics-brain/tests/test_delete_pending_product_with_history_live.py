"""Requires docker compose up + a running server on port 9000. Regression
for a real bug found live: DELETE /products/{id} on a PENDING product
(is_active=False, deleted_at=None) assumes nothing references it yet and
hard-deletes it. That assumption held only sometimes — a pending product
that already accumulated a product_price_history row (e.g. a rollup ran
before it was ever approved) hits the products<-product_price_history FK
and 500s the whole request. The merchant-facing symptom: the Discard button
on a Product Vision card does nothing, with zero error shown (the frontend
swallowed it silently — also fixed, see PendingProductCard.tsx).

Fix: fall back to the same soft-delete every non-pending product already
uses when the hard delete hits an IntegrityError, instead of crashing.
A mocked unit test can't exercise a genuine FK violation — this needs real
Postgres."""
import time
import uuid
import httpx

BASE = "http://127.0.0.1:9000"


def test_discard_succeeds_when_pending_product_has_price_history():
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import get_settings
    from app.models.db_models import ProductDB, ProductPriceHistoryDB

    async def _seed_pending_product_with_history(merchant_id: str) -> str:
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        product_id = f"prod_{uuid.uuid4().hex[:12]}"
        async with factory() as db:
            db.add(ProductDB(
                id=product_id, merchant_id=merchant_id, name="Vision Draft Widget",
                description="", price=50.0, cost_price=20.0, baseline_price=50.0,
                stock=5, category="misc", image_urls=[],
                is_active=False,  # pending — never approved
                created_at=int(time.time() * 1000),
            ))
            db.add(ProductPriceHistoryDB(
                id=f"pph_{uuid.uuid4().hex[:12]}", product_id=product_id,
                date="2026-07-19", views=3, cart_adds=0, purchases=0,
                price_active=50.0,
            ))
            await db.commit()
        await engine.dispose()
        return product_id

    email = f"deletependinghist_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Delete Pending History Test Co", "password": "a-strong-password",
        })
        assert r.status_code == 201, r.text
        merchant_id = r.json()["id"]

        product_id = asyncio.run(_seed_pending_product_with_history(merchant_id))

        r = c.delete(f"/products/{product_id}")
        assert r.status_code == 204, r.text

        # Soft-deleted, not gone — the price history row must still resolve.
        r = c.get("/products/pending")
        assert r.status_code == 200, r.text
        assert all(p["id"] != product_id for p in r.json())

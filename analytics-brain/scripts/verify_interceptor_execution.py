"""
Manual verification: the execution-time interceptor re-check actually blocks
an unsafe promo. Run against the local dev stack (docker compose up first).

Usage:
    docker compose exec api python -m scripts.verify_interceptor_execution
"""
import asyncio
import time
from uuid import uuid4

from app.core.database import get_session_factory
from app.core.redis import get_redis
from app.models.db_models import AgentActionDB, MerchantDB, ProductDB
from app.models.schemas import SystemState
from app.services import delta as delta_svc
from app.services.profile import save_constraints
from app.models.schemas import BusinessConstraints
from app.routers.agent import _execute_payload


async def main() -> None:
    factory = get_session_factory()
    async with factory() as db:
        merchant_id = "verify-interceptor-exec"
        merchant = await db.get(MerchantDB, merchant_id)
        if merchant is None:
            merchant = MerchantDB(id=merchant_id, email="verify@example.com",
                                   hashed_password="x", store_name="Verify Store", slug="verify-store")
            db.add(merchant)
            await db.flush()

        product_id = "verify-thin-margin"
        product = await db.get(ProductDB, product_id)
        if product is None:
            product = ProductDB(id=product_id, merchant_id=merchant_id, name="Thin Margin Widget",
                                 price=20.0, cost_price=18.0, stock=10)
            db.add(product)
            await db.flush()

        await save_constraints(db, merchant_id, BusinessConstraints(max_discount_percent=40))
        await db.commit()

        state = SystemState(last_updated=int(time.time() * 1000),
                             products={product_id: __import__("app.services.products", fromlist=["db_to_product"]).db_to_product(product)})
        await delta_svc.save_state(merchant_id, state)

        row = AgentActionDB(
            id=str(uuid4()), merchant_id=merchant_id, promo_id=f"VERIFY_{uuid4().hex[:6]}",
            action_type="flash_sale", trigger="manual verify", title="t", description="d",
            estimated_gmv=0, estimated_confidence=0.5,
            payload={"product_id": product_id, "discount_percent": 40}, brand_check="",
            status="pending", created_at=int(time.time() * 1000),
        )
        db.add(row)
        await db.commit()

        applied = await _execute_payload(row, db)
        # cost=18, price=20: even the 40% ceiling clamp -> $12, well below $18 cost.
        print(f"applied={applied} (expected False — 40% off $20 sells at $12, below $18 cost)")
        assert applied is False, "Expected the execution-time re-check to block this promo"
        print("PASS: execution-time interceptor re-check correctly blocked an unsafe promo")


if __name__ == "__main__":
    asyncio.run(main())

"""Fixture for the browser money-shot test. Creates a PENDING recovery_offer
action for owoyemi (so the UI drive can approve it live), or cleans everything up.

  create  -> prints ACTION_ID=<uuid>  (a pending recovery_offer, promo DEMO_RECOV_UI)
  cleanup -> removes the action, its test order, the recovery state, demo carts

Run: docker compose exec api sh -c "cd /app && python -m scripts.recovery_ui_fixture create"
"""
import asyncio
import sys
import time
import uuid

from sqlalchemy import select, delete

from app.core.database import get_session_factory
from app.core.redis import get_redis
from app.models.db_models import MerchantDB, AgentActionDB, OrderDB
from app.services import delta as delta_svc

SLUG = "owoyemi-of-offa"
PROMO_ID = "DEMO_RECOV_UI"


async def create():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == SLUG))
        await db.execute(delete(AgentActionDB).where(
            AgentActionDB.merchant_id == m.id, AgentActionDB.status == "pending"))
        aid = str(uuid.uuid4())
        db.add(AgentActionDB(
            id=aid, merchant_id=m.id, promo_id=PROMO_ID,
            action_type="recovery_offer", trigger="cart-abandon surge",
            title="Recover Abandoned Carts", description="Come back — 10% off your order",
            estimated_gmv=120.0, estimated_confidence=0.82,
            payload={"discount_percent": 10, "duration_minutes": 10},
            brand_check="on-brand", status="pending",
            created_at=int(time.time() * 1000), trigger_description="cart-abandon surge",
        ))
        await db.commit()
        print(f"ACTION_ID={aid}")


async def cleanup():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == SLUG))
        await db.execute(delete(AgentActionDB).where(AgentActionDB.promo_id == PROMO_ID))
        await db.execute(delete(OrderDB).where(
            OrderDB.merchant_id == m.id, OrderDB.customer_email == "uitester@test.dev"))
        await db.commit()
        state = await delta_svc.load_state(m.id)
        if state:
            state.recovery = None
            await delta_svc.save_state(m.id, state)
    # wipe any demo carts we created
    redis = await get_redis()
    async for key in redis.scan_iter(match="cart:*uitest*"):
        await redis.delete(key)
    print("cleaned up")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "create"
    asyncio.run(create() if cmd == "create" else cleanup())

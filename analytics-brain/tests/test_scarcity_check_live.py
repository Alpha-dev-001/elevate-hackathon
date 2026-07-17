"""Requires docker compose up + a real Qwen API key configured. Proves
mechanism 3 end-to-end: a genuinely low-stock, high-view-velocity product
actually produces a scarcity_price proposal via a real Qwen call, tagged
pricing_strategist. A mocked test (test_scarcity_check.py) proves the
WIRING; only a real call proves Qwen actually reasons its way to
propose_scarcity_price given the joint signal, which is the whole point.
"""
import time
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_low_stock_high_demand_product_produces_a_scarcity_price_proposal():
    from app.core.config import get_settings
    from app.core.redis import get_redis, Keys
    from app.models.db_models import MerchantDB, ProductDB, AgentActionDB, ReceiptDB
    from app.services.behavior_tracker import ANOMALY_THRESHOLD
    from app.services.store_review import check_scarcity_signals

    async def _scenario():
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        redis = await get_redis()

        merchant_id = f"merchant_scarcetest_{uuid.uuid4().hex[:10]}"
        p1_id = f"prod_scarcetest_{uuid.uuid4().hex[:8]}"

        async with factory() as db:
            db.add(MerchantDB(
                id=merchant_id,
                email=f"scarcetest-{int(time.time() * 1000)}@elevate.com",
                hashed_password="x",
                store_name="Scarcity Test Store",
                slug=f"scarcetest-{int(time.time() * 1000)}",
                is_live=True,
            ))
            db.add(ProductDB(
                id=p1_id, merchant_id=merchant_id, name="Limited Run Sneaker",
                price=120.0, baseline_price=120.0, cost_price=50.0, stock=2,
                is_active=True, category="fashion",
            ))
            await db.commit()

        # Seed real recent view events so count_per_product_views_in_window
        # sees genuine demand for this exact product — the same Redis event
        # list behavior_tracker's other callers already read from.
        import json
        now = time.time()
        for i in range(ANOMALY_THRESHOLD * 4 + 5):
            await redis.lpush(Keys.events(merchant_id), json.dumps({
                "event_type": "view", "product_id": p1_id, "timestamp": now - i,
            }))

        try:
            async with factory() as db:
                action = await check_scarcity_signals(merchant_id, db, redis)

            assert action is not None, (
                "Qwen declined propose_scarcity_price given a genuinely low-"
                "stock, high-view product — re-run once (real-model variance); "
                "if it fails a second time, the joint condition or anomaly "
                "wording needs adjustment, not the wiring"
            )
            assert action.action_type.value == "scarcity_price"
            assert action.role == "pricing_strategist"

            async with factory() as db:
                row = await db.get(AgentActionDB, action.id)
                assert row.role == "pricing_strategist"
                assert row.action_type == "scarcity_price"
        finally:
            async with factory() as db:
                from sqlalchemy import delete
                await db.execute(delete(ReceiptDB).where(ReceiptDB.merchant_id == merchant_id))
                await db.execute(delete(AgentActionDB).where(AgentActionDB.merchant_id == merchant_id))
                await db.execute(delete(ProductDB).where(ProductDB.merchant_id == merchant_id))
                await db.execute(delete(MerchantDB).where(MerchantDB.id == merchant_id))
                await db.commit()
            await redis.delete(Keys.events(merchant_id))
            await redis.delete(Keys.scarcity_checked(p1_id, time.strftime("%Y-%m-%d", time.gmtime())))
            await engine.dispose()

    _run(_scenario())

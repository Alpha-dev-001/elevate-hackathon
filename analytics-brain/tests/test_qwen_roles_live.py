"""Requires docker compose up + a real Qwen API key configured. Proves the
full chain end-to-end: role= actually restricts which tool Qwen can call,
and the resulting AgentActionDB row is actually tagged with that role. A
mocked test can prove the WIRING (call site passes role=X) but not that a
real Qwen response, constrained to a role's tool subset, actually produces
a row tagged with that same role — this is the only test in the plan that
makes a real API call end-to-end.

Inventory Overseer is used because it has exactly one tool
(propose_duplicate_merge) — Qwen structurally cannot return anything else,
which makes this test's outcome deterministic rather than dependent on
model judgment the way a Pricing Strategist or Sales Rep call (2-3 tools,
genuine choice) would be.
"""
import time
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_inventory_overseer_role_produces_a_correctly_tagged_duplicate_merge():
    from app.core.config import get_settings
    from app.core.redis import get_redis
    from app.models.db_models import MerchantDB, ProductDB, AgentActionDB, ReceiptDB
    from app.services.decision_engine import run_decision_cycle
    from app.services.qwen_roles import INVENTORY_OVERSEER

    async def _scenario():
        # Throwaway engine — not app.core.database's process-global cached
        # one, which breaks across separate asyncio.run() calls from other
        # "_live" tests in the same pytest process ("attached to a
        # different loop"). See test_capability_tracker_live.py.
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        redis = await get_redis()

        merchant_id = f"merchant_roletest_{uuid.uuid4().hex[:10]}"
        p1_id = f"prod_roletest_a_{uuid.uuid4().hex[:8]}"
        p2_id = f"prod_roletest_b_{uuid.uuid4().hex[:8]}"

        async with factory() as db:
            db.add(MerchantDB(
                id=merchant_id,
                email=f"roletest-{int(time.time() * 1000)}@elevate.com",
                hashed_password="x",
                store_name="Role Test Store",
                slug=f"roletest-{int(time.time() * 1000)}",
                is_live=True,
            ))
            db.add(ProductDB(
                id=p1_id, merchant_id=merchant_id, name="Blue Ceramic Mug",
                price=15.0, baseline_price=15.0, cost_price=6.0, stock=10, is_active=True,
            ))
            db.add(ProductDB(
                id=p2_id, merchant_id=merchant_id, name="Blue Ceramic Mug",
                price=15.0, baseline_price=15.0, cost_price=6.0, stock=8, is_active=True,
            ))
            await db.commit()

        try:
            async with factory() as db:
                action = await run_decision_cycle(
                    merchant_id,
                    f'Duplicate listings: 2 entries for "Blue Ceramic Mug" — '
                    f"{p1_id} (stock: 10), {p2_id} (stock: 8) — same product listed under separate entries",
                    db, redis,
                    role=INVENTORY_OVERSEER,
                )

            assert action is not None, "Qwen declined to call the only tool it had — re-run, or check the anomaly description is clear enough"
            assert action.action_type.value == "duplicate_merge"
            assert action.role == "inventory_overseer"

            async with factory() as db:
                row = await db.get(AgentActionDB, action.id)
                assert row.role == "inventory_overseer"
                assert row.action_type == "duplicate_merge"
        finally:
            async with factory() as db:
                from sqlalchemy import delete
                # receipts must go first — FK references merchants.id, same
                # gotcha documented in project memory for manual live-test
                # cleanup (agent_actions/receipts/products before merchant).
                await db.execute(delete(ReceiptDB).where(ReceiptDB.merchant_id == merchant_id))
                await db.execute(delete(AgentActionDB).where(AgentActionDB.merchant_id == merchant_id))
                await db.execute(delete(ProductDB).where(ProductDB.merchant_id == merchant_id))
                await db.execute(delete(MerchantDB).where(MerchantDB.id == merchant_id))
                await db.commit()
            await engine.dispose()

    _run(_scenario())

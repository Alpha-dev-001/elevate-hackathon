"""Requires docker compose up + a real Qwen API key configured. Proves the
full escalation chain end-to-end against a real model: a deliberately
unambiguous case where the RIGHT fix is a price change, not layout/copy —
Store Curator should recognize its own tools don't fit and hand off to
Pricing Strategist. A mocked test (test_role_escalation.py) proves the
WIRING; only a real call proves a real model actually chooses to escalate
given genuine ambiguity, which is the whole point of this mechanism.
"""
import time
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_store_curator_escalates_an_overpriced_underperformer_to_pricing_strategist():
    from app.core.config import get_settings
    from app.core.redis import get_redis
    from app.models.db_models import MerchantDB, ProductDB, AgentActionDB, ReceiptDB
    from app.services.decision_engine import run_decision_cycle
    from app.services.qwen_roles import STORE_CURATOR

    async def _scenario():
        # Throwaway engine — not app.core.database's process-global cached
        # one, which breaks across separate asyncio.run() calls from other
        # "_live" tests in the same pytest process. See test_qwen_roles_live.py.
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        redis = await get_redis()

        merchant_id = f"merchant_esctest_{uuid.uuid4().hex[:10]}"
        p1_id = f"prod_esctest_a_{uuid.uuid4().hex[:8]}"
        p2_id = f"prod_esctest_b_{uuid.uuid4().hex[:8]}"
        p3_id = f"prod_esctest_c_{uuid.uuid4().hex[:8]}"

        async with factory() as db:
            db.add(MerchantDB(
                id=merchant_id,
                email=f"esctest-{int(time.time() * 1000)}@elevate.com",
                hashed_password="x",
                store_name="Escalation Test Store",
                slug=f"esctest-{int(time.time() * 1000)}",
                is_live=True,
            ))
            # Two ordinary category peers at a normal price...
            db.add(ProductDB(
                id=p1_id, merchant_id=merchant_id, name="Standard Ceramic Mug",
                price=15.0, baseline_price=15.0, cost_price=6.0, stock=20,
                is_active=True, category="home",
            ))
            db.add(ProductDB(
                id=p2_id, merchant_id=merchant_id, name="Classic Ceramic Mug",
                price=16.0, baseline_price=16.0, cost_price=6.0, stock=18,
                is_active=True, category="home",
            ))
            # ...and one wildly overpriced twin with real interest but zero
            # conversions — the actual fix is an obvious price cut, not a
            # layout/copy change, which Store Curator has no tool for.
            db.add(ProductDB(
                id=p3_id, merchant_id=merchant_id, name="Premium Ceramic Mug",
                price=95.0, baseline_price=95.0, cost_price=6.0, stock=20,
                is_active=True, category="home",
            ))
            await db.commit()

        try:
            async with factory() as db:
                action = await run_decision_cycle(
                    merchant_id,
                    'Store review: 42 views, 0 orders in the last 24h for "Premium '
                    'Ceramic Mug" — high interest, no conversion. Note: this product '
                    'is priced at $95 vs $15-16 for near-identical category peers '
                    '(Standard/Classic Ceramic Mug) with the same cost basis — the '
                    "price itself, not the presentation, is the likely reason for "
                    "zero conversions despite real interest.",
                    db, redis,
                    role=STORE_CURATOR,
                )

            assert action is not None, (
                "Qwen did not propose or escalate — re-run once (real-model "
                "variance); if it fails a second time, the anomaly description "
                "needs to make the price mismatch even more unambiguous, not "
                "the escalation-wiring code"
            )
            assert action.role == "pricing_strategist", (
                f"expected Store Curator to escalate to Pricing Strategist, "
                f"got role={action.role!r}, action_type={action.action_type!r}"
            )
            assert "[Escalated from store_curator]" in action.reasoning

            async with factory() as db:
                row = await db.get(AgentActionDB, action.id)
                assert row.role == "pricing_strategist"
        finally:
            async with factory() as db:
                from sqlalchemy import delete
                await db.execute(delete(ReceiptDB).where(ReceiptDB.merchant_id == merchant_id))
                await db.execute(delete(AgentActionDB).where(AgentActionDB.merchant_id == merchant_id))
                await db.execute(delete(ProductDB).where(ProductDB.merchant_id == merchant_id))
                await db.execute(delete(MerchantDB).where(MerchantDB.id == merchant_id))
                await db.commit()
            await engine.dispose()

    _run(_scenario())

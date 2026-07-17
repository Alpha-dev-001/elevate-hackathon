"""Requires docker compose up (real Postgres + Redis). End-to-end proof of
the fix for a real bug found live: rollup_daily_signals and
flag_suspicious_signals were both fully written and unit-tested but never
called from anywhere in the app, so product_price_history always had 0 rows
and is_price_rebalance_eligible was unconditionally False forever —
price_rebalance had literally never fired in production. This test seeds a
real purchase, runs the now-wired run_daily_rollup_if_due for that date, and
proves eligibility actually flips to True — the thing pure unit tests of the
underlying functions could never have caught, since the gap was in wiring,
not logic.
"""
import time
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_purchase_then_rollup_makes_price_rebalance_eligible():
    from app.core.config import get_settings
    from app.models.db_models import MerchantDB, ProductDB, OrderDB
    from app.services.pricing_signals import rollup_daily_signals, _yesterday_utc
    from app.services.pricing_cycle import check_eligibility

    async def _scenario():
        # A throwaway engine — not app.core.database's process-global cached
        # one, which breaks across separate asyncio.run() calls from other
        # "_live" tests in the same pytest process ("attached to a different
        # loop"). See test_capability_tracker_live.py for the full mechanism.
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

        # The real Redis (via docker compose) is fine to use here: rollup_
        # daily_signals only touches Keys.events(merchant_id) (merchant-scoped,
        # this throwaway merchant has none, which is fine — the purchase count
        # comes from OrderDB, not Redis) and writes ProductPriceHistoryDB rows
        # directly. Deliberately calling rollup_daily_signals directly rather
        # than run_daily_rollup_if_due, which gates on a GLOBAL (not merchant-
        # scoped) "last rollup date" key shared with the real running app —
        # using that gate here would flakily skip if the real background loop
        # already rolled up today. The gate itself is covered separately by
        # TestRunDailyRollupIfDue's mocked tests in test_pricing_signals.py.
        from app.core.redis import get_redis
        redis = await get_redis()

        merchant_id = f"merchant_rolluptest_{uuid.uuid4().hex[:10]}"
        product_id = f"prod_rolluptest_{uuid.uuid4().hex[:10]}"
        yesterday = _yesterday_utc()
        # OrderDB.created_at must fall within [yesterday 00:00, yesterday 24:00)
        # UTC for purchase_counts_for_date to pick it up.
        from datetime import datetime, timezone
        order_ts = int(
            datetime.strptime(yesterday, "%Y-%m-%d")
            .replace(tzinfo=timezone.utc, hour=12)
            .timestamp() * 1000
        )

        async with factory() as db:
            db.add(MerchantDB(
                id=merchant_id,
                email=f"rolluptest-{int(time.time() * 1000)}@elevate.com",
                hashed_password="x",
                store_name="Rollup Test Store",
                slug=f"rolluptest-{int(time.time() * 1000)}",
                is_live=True,
            ))
            db.add(ProductDB(
                id=product_id,
                merchant_id=merchant_id,
                name="Rollup Test Widget",
                price=20.0,
                baseline_price=20.0,
                cost_price=8.0,
                stock=10,
                is_active=True,
            ))
            db.add(OrderDB(
                id=f"order_{uuid.uuid4().hex[:10]}",
                merchant_id=merchant_id,
                session_id="sess-rolluptest",
                items=[{"product_id": product_id, "qty": 1}],
                total=20.0,
                status="paid",
                created_at=order_ts,
            ))
            await db.commit()

        try:
            # Before the fix's target: no rollup has run, so no history exists.
            async with factory() as db:
                eligible_before = await check_eligibility(product_id, db)
            assert eligible_before is False

            async with factory() as db:
                written = await rollup_daily_signals(db, redis, target_date=yesterday)
            assert written >= 1

            async with factory() as db:
                eligible_after = await check_eligibility(product_id, db)
            assert eligible_after is True, (
                "product_price_history row was written but eligibility still "
                "false — the purchase count didn't make it through the rollup"
            )
        finally:
            async with factory() as db:
                from sqlalchemy import delete
                from app.models.db_models import ProductPriceHistoryDB
                await db.execute(delete(OrderDB).where(OrderDB.merchant_id == merchant_id))
                await db.execute(delete(ProductPriceHistoryDB).where(ProductPriceHistoryDB.product_id == product_id))
                await db.execute(delete(ProductDB).where(ProductDB.merchant_id == merchant_id))
                await db.execute(delete(MerchantDB).where(MerchantDB.id == merchant_id))
                await db.commit()
            await engine.dispose()

    _run(_scenario())

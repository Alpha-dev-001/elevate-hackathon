"""Requires docker compose up (real Postgres). Regression test for the same
shallow-copy bug fixed in search_tracker.py — capability_tracker.record_unmet
used the identical broken pattern (reqs.get(key) returning a shared nested-
dict reference instead of a fresh copy), so PROPOSE_THRESHOLD (2) could never
actually be reached in production: the second identical unmet-capability ask
silently failed to increment the persisted count. Found while tracing the
search-tracker bug, since capability_tracker.py was the template it was
copied from. Uses the app's real session factory directly (no Qwen/brand
setup needed) rather than going through the full edit-intent HTTP flow.
"""
import asyncio
import time
import uuid


def _run(coro):
    return asyncio.run(coro)


def test_repeated_identical_capability_ask_increments_count():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import get_settings
    from app.models.db_models import MerchantDB
    from app.services.capability_tracker import record_unmet

    async def _scenario():
        # A throwaway engine, not app.core.database's process-global cached
        # one — that engine's asyncpg pool binds to whichever event loop
        # first used it, and reusing it across separate asyncio.run() calls
        # from OTHER "_live" tests in the same pytest process breaks with
        # "attached to a different loop". Production never hits this: the
        # real app's event loop never changes for the process lifetime.
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        merchant_id = f"merchant_captrack_{uuid.uuid4().hex[:12]}"

        async with factory() as db:
            db.add(MerchantDB(
                id=merchant_id,
                email=f"captrack-live-{int(time.time() * 1000)}@elevate.com",
                hashed_password="x",
                store_name="Capability Tracker Live Test",
                slug=f"captrack-live-{int(time.time() * 1000)}",
            ))
            await db.commit()

        try:
            async with factory() as db:
                r1 = await record_unmet(merchant_id, "testimonials section", "add reviews first", db)
            assert r1["count"] == 1
            assert r1["proposed"] is False

            async with factory() as db:
                r2 = await record_unmet(merchant_id, "testimonials section", "add reviews second", db)
            assert r2["count"] == 2, f"expected count=2 on the second identical ask, got {r2}"
            assert r2["proposed"] is True, "PROPOSE_THRESHOLD=2 must flip status once reached"
        finally:
            async with factory() as db:
                row = await db.get(MerchantDB, merchant_id)
                if row:
                    await db.delete(row)
                    await db.commit()
            await engine.dispose()

    _run(_scenario())

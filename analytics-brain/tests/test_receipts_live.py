"""Requires docker compose up + a running server on port 9000. Real-DB
coverage for verify_row_consistency — the DB-coupled half of the Decision
Ledger that test_receipts.py's pure-function suite can't exercise. Same
throwaway-engine convention as test_decision_log_live.py's context_snapshot
test (the process-global engine binds to whichever event loop first used
it, and a later asyncio.run() call breaks that binding).

Regression coverage for the bug where verify_row_consistency compared EVERY
receipt for an action against the row's current state, so any action that
had legitimately moved past "proposed" always failed — even with zero
tampering. The fix: only the action's most recent receipt is checked
against the live row.
"""
import uuid
import httpx

BASE = "http://127.0.0.1:9000"


def _engine_and_factory():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


def _signup(store_name: str) -> str:
    email = f"receiptslive_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": store_name, "password": "a-strong-password",
        })
        assert r.status_code == 201, r.text
        return r.json()["id"]


def test_lifecycle_receipts_do_not_falsely_mismatch():
    """proposed -> executed is the normal path: two receipts for one
    action, the row's final content matches only the LATEST one. Before the
    fix, the stale "proposed" receipt was compared against the current
    (executed) row and always failed."""
    import asyncio
    from app.services.receipts import append_receipt, verify_chain, verify_row_consistency
    from app.models.db_models import AgentActionDB

    async def _run(merchant_id: str) -> list[str]:
        engine, factory = _engine_and_factory()
        async with factory() as db:
            row = AgentActionDB(
                id=f"aa_{uuid.uuid4().hex[:12]}",
                merchant_id=merchant_id,
                promo_id=f"ELEV_TEST_{uuid.uuid4().hex[:6].upper()}",
                action_type="flash_sale",
                trigger="t", title="t", description="d",
                estimated_gmv=0.0, estimated_confidence=0.5,
                payload={"discount_percent": 15}, brand_check="", constraint_check="",
                status="pending",
            )
            db.add(row)
            await db.flush()

            await append_receipt(db, merchant_id, "proposed", action_row=row)

            row.status = "executed"
            row.constraint_check = "ok"
            await db.flush()
            await append_receipt(db, merchant_id, "executed", action_row=row)
            await db.commit()

        async with factory() as db:
            from sqlalchemy import select
            from app.models.db_models import ReceiptDB
            result = await db.execute(
                select(ReceiptDB).where(ReceiptDB.merchant_id == merchant_id).order_by(ReceiptDB.sequence)
            )
            receipts = list(result.scalars())
            valid, err = verify_chain(receipts)
            assert valid, err
            mismatches = await verify_row_consistency(db, receipts)

        await engine.dispose()
        return mismatches

    merchant_id = _signup("Receipts Live Test Co")
    mismatches = asyncio.run(_run(merchant_id))
    assert mismatches == []


def test_edit_after_final_receipt_is_still_caught():
    """A genuine after-the-fact edit to the row's content post-dates its
    LATEST receipt — this must still be flagged, so the fix can't have
    swung from false positives to blindness."""
    import asyncio
    from app.services.receipts import append_receipt, verify_row_consistency
    from app.models.db_models import AgentActionDB

    async def _run(merchant_id: str) -> list[str]:
        engine, factory = _engine_and_factory()
        async with factory() as db:
            row = AgentActionDB(
                id=f"aa_{uuid.uuid4().hex[:12]}",
                merchant_id=merchant_id,
                promo_id=f"ELEV_TEST_{uuid.uuid4().hex[:6].upper()}",
                action_type="flash_sale",
                trigger="t", title="t", description="d",
                estimated_gmv=0.0, estimated_confidence=0.5,
                payload={"discount_percent": 15}, brand_check="", constraint_check="",
                status="executed",
            )
            db.add(row)
            await db.flush()
            await append_receipt(db, merchant_id, "executed", action_row=row)
            await db.commit()

            # Simulate quietly editing history after the receipt was written.
            row.payload = {"discount_percent": 90}
            await db.commit()

        async with factory() as db:
            from sqlalchemy import select
            from app.models.db_models import ReceiptDB
            result = await db.execute(
                select(ReceiptDB).where(ReceiptDB.merchant_id == merchant_id).order_by(ReceiptDB.sequence)
            )
            receipts = list(result.scalars())
            mismatches = await verify_row_consistency(db, receipts)

        await engine.dispose()
        return mismatches

    merchant_id = _signup("Receipts Live Test Co 2")
    mismatches = asyncio.run(_run(merchant_id))
    assert len(mismatches) == 1
    assert "content has changed" in mismatches[0]

"""Requires docker compose up + a running server on port 9000. Regression
for a real bug found live: dismissing a pending price_rebalance action whose
payload references a product_id that doesn't exist in the catalog (e.g. one
Qwen hallucinated) returned 500, even though the dismissal itself had
already committed successfully.

Root cause chain: outcome_observer.observe_outcome tries to reset the
product's trust streak on dismissal (update_trust_streak), which fails with
a real Postgres foreign-key violation because the product doesn't exist —
that's expected and already caught. But the except block's own logging line
referenced `action.id` (an ORM attribute), and by then the session's
transaction was poisoned by the failed write, so touching that attribute
triggered a lazy reload against a broken session — a SECOND exception from
inside the first except handler, which propagated all the way up to a 500.
Fixed by logging the plain string action_id parameter instead of the ORM
attribute, in both outcome_observer.py and agent.py's own except blocks.

This test reproduces the exact chain against a real Postgres session — a
mocked unit test can't exercise a genuine FK violation or session
poisoning."""
import time
import uuid
import httpx

BASE = "http://127.0.0.1:9000"


def test_dismiss_returns_200_when_referenced_product_does_not_exist():
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import get_settings
    from app.models.db_models import AgentActionDB

    async def _seed_bad_action(merchant_id: str) -> str:
        # Throwaway engine — see test_decision_log_live.py's own comment on
        # why the process-global cached engine breaks across separate
        # asyncio.run() calls from other "_live" tests in the same process.
        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        action_id = f"act_{uuid.uuid4().hex[:12]}"
        async with factory() as db:
            db.add(AgentActionDB(
                id=action_id, merchant_id=merchant_id,
                promo_id=f"ELEV_TEST_{uuid.uuid4().hex[:6].upper()}",
                action_type="price_rebalance",
                trigger="t", title="t", description="d",
                estimated_gmv=0.0, estimated_confidence=0.75,
                payload={"product_id": "prod_does_not_exist", "new_price": 52.5},
                brand_check="", constraint_check="", status="pending",
                created_at=int(time.time() * 1000),
            ))
            await db.commit()
        await engine.dispose()
        return action_id

    email = f"dismissbadref_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Dismiss Bad Ref Test Co", "password": "a-strong-password",
        })
        assert r.status_code == 201, r.text
        merchant_id = r.json()["id"]

        action_id = asyncio.run(_seed_bad_action(merchant_id))

        r = c.post(f"/api/agent/actions/{action_id}/dismiss")
        assert r.status_code == 200, r.text
        assert r.json()["action"]["status"] == "dismissed"

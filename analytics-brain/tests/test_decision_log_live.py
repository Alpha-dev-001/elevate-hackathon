"""Requires docker compose up + a running server on port 9000. First
automated coverage for GET /merchant/decisions — same httpx pytest-function
convention as test_memory_live.py / test_deduplicate_live.py."""
import uuid
import httpx

BASE = "http://127.0.0.1:9000"


def test_decisions_endpoint_shape_and_pagination():
    email = f"decisionlog_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Decision Log Test Co", "password": "a-strong-password",
            "category": "fashion", "description": "Test store for decision log coverage",
        })
        assert r.status_code == 201, r.text

        r = c.get("/merchant/decisions")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "decisions" in body and isinstance(body["decisions"], list)
        assert "total" in body and isinstance(body["total"], int)
        assert body["total"] == 0  # brand-new store, no actions yet

        r = c.get("/merchant/decisions?limit=5&offset=0")
        assert r.status_code == 200, r.text
        assert len(r.json()["decisions"]) <= 5


def test_decisions_endpoint_returns_context_snapshot():
    """context_snapshot carries what Qwen actually saw (catalog snapshot,
    prior-outcome memory, discount ceiling) alongside the reasoning output —
    added so the Decision Trace page can show inputs, not just outcomes."""
    import asyncio

    async def _make_decision(merchant_id: str):
        # A throwaway engine, not app.core.database's process-global cached
        # one — that engine's asyncpg pool binds to whichever event loop
        # first used it, and reusing it from a LATER, separate asyncio.run()
        # call (this test running after other "_live" tests in the same
        # pytest process) breaks with "attached to a different loop".
        # Production never hits this: the real app's event loop never
        # changes for the process lifetime.
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
        from app.core.config import get_settings
        from app.models.db_models import AgentActionDB

        engine = create_async_engine(get_settings().database_url)
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        async with factory() as db:
            db.add(AgentActionDB(
                id=f"aa_{uuid.uuid4().hex[:12]}",
                merchant_id=merchant_id,
                promo_id=f"ELEV_TEST_{uuid.uuid4().hex[:6].upper()}",
                action_type="flash_sale",
                trigger="t", title="t", description="d",
                estimated_gmv=0.0, estimated_confidence=0.5,
                payload={}, brand_check="", reasoning="because X",
                context_snapshot={"products_summary": "Widget ($10, stock: 5)", "max_discount_percent": 20.0},
            ))
            await db.commit()
        await engine.dispose()

    email = f"decisionctx_{uuid.uuid4().hex[:8]}@example.com"
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/signup", json={
            "email": email, "store_name": "Decision Context Test Co", "password": "a-strong-password",
        })
        assert r.status_code == 201, r.text
        merchant_id = r.json()["id"]

        asyncio.run(_make_decision(merchant_id))

        r = c.get("/merchant/decisions")
        assert r.status_code == 200, r.text
        decisions = r.json()["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["context_snapshot"]["products_summary"] == "Widget ($10, stock: 5)"
        assert decisions[0]["context_snapshot"]["max_discount_percent"] == 20.0

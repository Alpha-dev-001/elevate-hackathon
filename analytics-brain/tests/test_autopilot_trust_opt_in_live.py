"""Requires docker compose up + a running server on port 9000. Real-DB
coverage for the trust opt-in redesign: earning a streak unlocks the OPTION
to auto-apply, the merchant's own toggle (POST /products/{id}/autopilot-trust)
is what actually turns it on. Covers get_trust_state, set_auto_apply_enabled,
list_eligible_trust, and the two new endpoints — a mocked unit test can't
exercise the real upsert/unique-constraint behavior these need."""
import time
import uuid
import httpx

from app.services.autopilot_trust import TRUST_STREAK_THRESHOLD

BASE = "http://127.0.0.1:9000"


def _engine_and_factory():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.core.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    return engine, factory


def _signup_and_login(store_name: str) -> tuple[str, httpx.Client]:
    email = f"trustopt_{uuid.uuid4().hex[:8]}@example.com"
    password = "a-strong-password"
    c = httpx.Client(base_url=BASE, timeout=30)
    r = c.post("/auth/signup", json={"email": email, "store_name": store_name, "password": password})
    assert r.status_code == 201, r.text
    merchant_id = r.json()["id"]
    return merchant_id, c


def test_cannot_enable_below_threshold():
    import asyncio
    from app.services.autopilot_trust import set_auto_apply_enabled

    async def _run(merchant_id: str, product_id: str) -> str | None:
        engine, factory = _engine_and_factory()
        async with factory() as db:
            try:
                await set_auto_apply_enabled(merchant_id, product_id, "price_rebalance", True, db)
                return None
            except ValueError as e:
                return str(e)
            finally:
                await engine.dispose()

    merchant_id, c = _signup_and_login("Trust Opt Below Threshold Co")
    r = c.post("/products", json={
        "name": "Widget", "price": 20.0, "cost_price": 10.0, "stock": 10, "category": "misc",
    })
    assert r.status_code == 201, r.text
    product_id = r.json()["id"]

    err = asyncio.run(_run(merchant_id, product_id))
    assert err is not None
    assert "threshold" in err


def test_earn_streak_then_toggle_via_real_endpoint():
    import asyncio
    from app.services.autopilot_trust import update_trust_streak, get_trust_state

    async def _earn(merchant_id: str, product_id: str):
        engine, factory = _engine_and_factory()
        async with factory() as db:
            for _ in range(TRUST_STREAK_THRESHOLD):
                await update_trust_streak(
                    merchant_id, product_id, "price_rebalance", db,
                    approved=True, outcome_negative=False,
                )
        await engine.dispose()

    async def _read_state(merchant_id: str, product_id: str) -> tuple[int, bool]:
        engine, factory = _engine_and_factory()
        async with factory() as db:
            state = await get_trust_state(merchant_id, product_id, "price_rebalance", db)
        await engine.dispose()
        return state

    merchant_id, c = _signup_and_login("Trust Opt Toggle Co")
    r = c.post("/products", json={
        "name": "Gadget", "price": 30.0, "cost_price": 15.0, "stock": 10, "category": "misc",
    })
    assert r.status_code == 201, r.text
    product_id = r.json()["id"]

    asyncio.run(_earn(merchant_id, product_id))
    streak, enabled = asyncio.run(_read_state(merchant_id, product_id))
    assert streak == TRUST_STREAK_THRESHOLD
    assert enabled is False  # earned, but not yet opted in

    # Not eligible-list-worthy until earned — now it should appear, still off.
    r = c.get("/products/autopilot-trust")
    assert r.status_code == 200, r.text
    eligible = r.json()["eligible"]
    row = next(e for e in eligible if e["product_id"] == product_id)
    assert row["streak"] == TRUST_STREAK_THRESHOLD
    assert row["auto_apply_enabled"] is False

    # The merchant's own opt-in.
    r = c.post(f"/products/{product_id}/autopilot-trust", json={"action_type": "price_rebalance", "enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True

    streak2, enabled2 = asyncio.run(_read_state(merchant_id, product_id))
    assert streak2 == TRUST_STREAK_THRESHOLD
    assert enabled2 is True

    # And back off again — always allowed, no threshold check.
    r = c.post(f"/products/{product_id}/autopilot-trust", json={"action_type": "price_rebalance", "enabled": False})
    assert r.status_code == 200, r.text
    _, enabled3 = asyncio.run(_read_state(merchant_id, product_id))
    assert enabled3 is False


def test_toggle_endpoint_404s_for_another_merchants_product():
    merchant_a, client_a = _signup_and_login("Trust Opt Owner Co")
    r = client_a.post("/products", json={
        "name": "Owned Widget", "price": 20.0, "cost_price": 10.0, "stock": 10, "category": "misc",
    })
    assert r.status_code == 201, r.text
    product_id = r.json()["id"]

    _merchant_b, client_b = _signup_and_login("Trust Opt Intruder Co")
    r = client_b.post(f"/products/{product_id}/autopilot-trust", json={"action_type": "price_rebalance", "enabled": True})
    assert r.status_code == 404, r.text

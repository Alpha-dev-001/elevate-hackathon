"""Live end-to-end test of the autopilot money-shot WebSocket:
connect a storefront client → approve an action via REST (server broadcasts) →
assert the client receives state_updated carrying the new promo.

Run: docker compose exec api sh -c "cd /app && python -m scripts.test_ws_moneyshot"
"""
import asyncio
import json
import time
import uuid

import httpx
import websockets
from sqlalchemy import select, delete
from app.core.database import get_session_factory
from app.models.db_models import MerchantDB, AgentActionDB


async def main():
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == "owoyemi-of-offa"))
        mid = m.id
        await db.execute(
            delete(AgentActionDB).where(
                AgentActionDB.merchant_id == mid, AgentActionDB.status == "pending"
            )
        )
        aid = str(uuid.uuid4())
        db.add(AgentActionDB(
            id=aid, merchant_id=mid, promo_id=f"TESTWS_{uuid.uuid4().hex[:4].upper()}",
            action_type="recovery_offer", trigger="cart-abandon surge (test)",
            title="Recover Abandoned Carts with Offer", description="Come back — 10% off",
            estimated_gmv=120.0, estimated_confidence=0.82,
            payload={"discount_percent": 10, "duration_minutes": 10},
            brand_check="on-brand", status="pending",
            created_at=int(time.time() * 1000), trigger_description="test",
        ))
        await db.commit()

    uri = f"ws://localhost:9000/ws/storefront/{mid}"
    async with websockets.connect(uri) as ws:
        initial = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        ip = initial.get("payload", {}).get("state", {}).get("active_promos", {})
        print(f"[1] connected → initial '{initial.get('event')}', promos={len(ip)}")

        async with httpx.AsyncClient() as client:
            r = await client.post(f"http://localhost:9000/api/agent/actions/{aid}/approve", timeout=20)
            print(f"[2] approve → HTTP {r.status_code}")

        update = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        promos = update.get("payload", {}).get("state", {}).get("active_promos", {})
        label = next(iter(promos.values()), {}).get("label") if promos else None
        ok = update.get("event") == "state_updated" and bool(promos)
        print(f"[3] storefront received '{update.get('event')}', promos={len(promos)} label={label!r}")
        print("MONEY-SHOT WS:", "WORKS ✅" if ok else "FAILED ❌")

    # cleanup: remove the test promo so demo state stays clean
    from app.services import delta as delta_svc
    async with get_session_factory()() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == "owoyemi-of-offa"))
        state = await delta_svc.load_state(m.id)
        if state:
            state.active_promos.clear()
            await delta_svc.save_state(m.id, state)
    print("[4] cleaned up test promo")


if __name__ == "__main__":
    asyncio.run(main())

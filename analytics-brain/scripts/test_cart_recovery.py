"""Live end-to-end test of the ORDER-LEVEL cart-recovery money-shot.

Builds a real 2-item cart → approves a real recovery_offer via REST (the real
agent path sets SystemState.recovery + broadcasts) → asserts the SAME cart's
total drops (browse products stay full price) → checks out and asserts the order
total is discounted AND attributes to the recovery action in the dashboard.

Run: docker compose exec api sh -c "cd /app && python -m scripts.test_cart_recovery"
"""
import asyncio
import time
import uuid

import httpx
from sqlalchemy import select, delete

from app.core.database import get_session_factory
from app.models.db_models import MerchantDB, ProductDB, OrderDB, AgentActionDB
from app.models.schemas import OrderCustomer
from app.services import cart as cart_svc
from app.services import orders as orders_svc
from app.services import delta as delta_svc

SLUG = "owoyemi-of-offa"
SESSION = f"recovtest_{uuid.uuid4().hex[:8]}"


def check(name: str, cond: bool) -> bool:
    print(f"  {'✅' if cond else '❌'} {name}")
    return cond


async def main():
    ok = True
    factory = get_session_factory()

    async with factory() as db:
        m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == SLUG))
        mid = m.id
        prods = (await db.scalars(
            select(ProductDB).where(ProductDB.merchant_id == mid, ProductDB.is_active == True).limit(2)
        )).all()
        p1, p2 = prods[0], prods[1]

    # ── 1. Build a real cart (2 items) ──────────────────────────────────────
    async with factory() as db:
        await cart_svc.add_item(db, mid, SESSION, p1.id, 1)
        cart = await cart_svc.add_item(db, mid, SESSION, p2.id, 1)
    subtotal_before = cart.subtotal
    print(f"[1] cart built: {cart.item_count} items, subtotal=${subtotal_before}")
    ok &= check("no discount before recovery", cart.discount_amount == 0 and cart.total == subtotal_before)

    # ── 2. Create + approve a real recovery_offer action ────────────────────
    promo_id = f"RECOV_{uuid.uuid4().hex[:5].upper()}"
    aid = str(uuid.uuid4())
    async with factory() as db:
        await db.execute(delete(AgentActionDB).where(
            AgentActionDB.merchant_id == mid, AgentActionDB.status == "pending"))
        db.add(AgentActionDB(
            id=aid, merchant_id=mid, promo_id=promo_id,
            action_type="recovery_offer", trigger="cart-abandon surge (test)",
            title="Recover Abandoned Carts", description="Come back — 10% off",
            estimated_gmv=120.0, estimated_confidence=0.82,
            payload={"discount_percent": 10, "duration_minutes": 10},
            brand_check="on-brand", status="pending",
            created_at=int(time.time() * 1000), trigger_description="test",
        ))
        await db.commit()

    async with httpx.AsyncClient() as client:
        r = await client.post(f"http://localhost:9000/api/agent/actions/{aid}/approve", timeout=30)
    print(f"[2] approve recovery_offer → HTTP {r.status_code}")
    ok &= check("approve succeeded", r.status_code == 200)

    # ── 3. The SAME cart now carries the discount; products stay full price ──
    async with factory() as db:
        cart2 = await cart_svc.get_cart(mid, SESSION)
    expected_amt = round(subtotal_before * 0.10, 2)
    print(f"[3] cart after: subtotal=${cart2.subtotal} discount={cart2.discount_percent}% "
          f"(-${cart2.discount_amount}) total=${cart2.total} label={cart2.discount_label!r}")
    ok &= check("discount_percent is 10", cart2.discount_percent == 10)
    ok &= check("discount_amount correct", cart2.discount_amount == expected_amt)
    ok &= check("total dropped by discount", cart2.total == round(subtotal_before - expected_amt, 2))
    ok &= check("subtotal unchanged (lines untouched)", cart2.subtotal == subtotal_before)
    ok &= check("countdown has an expiry", bool(cart2.discount_expires_at))

    # browse grid must NOT be discounted (recovery is order-level, not a promo)
    r_store = httpx.get(f"http://localhost:9000/api/store/{SLUG}", timeout=10).json()
    discounted_products = [p for p in r_store["products"] if p.get("compare_at_price")]
    ok &= check("browse grid untouched (0 products discounted)", len(discounted_products) == 0)
    ok &= check("store payload exposes recovery banner", bool(r_store.get("recovery")))

    # ── 4. Checkout under the offer → discounted total + attribution ────────
    async with factory() as db:
        order = await orders_svc.checkout(
            db, mid, SESSION, OrderCustomer(name="Recovery Tester", email="recov@test.dev"))
    print(f"[4] order {order.id}: subtotal=${order.subtotal} total=${order.total} "
          f"promo_applied={order.promo_applied!r}")
    ok &= check("order total is discounted", order.total == round(subtotal_before - expected_amt, 2))
    ok &= check("order attributes to recovery promo_id", order.promo_applied == promo_id)

    async with httpx.AsyncClient() as client:
        dash = (await client.get(f"http://localhost:9000/api/dashboard/{SLUG}", timeout=10)).json()
    row = next((a for a in dash["actions"] if a["promo_id"] == promo_id), None)
    print(f"[5] dashboard: attributed_gmv=${row['attributed_gmv'] if row else None} "
          f"orders={row['attributed_orders'] if row else 0}")
    ok &= check("dashboard attributes the recovery revenue",
                bool(row) and row["attributed_gmv"] == order.total and row["attributed_orders"] >= 1)

    # ── cleanup ─────────────────────────────────────────────────────────────
    async with factory() as db:
        await db.execute(delete(OrderDB).where(OrderDB.id == order.id))
        await db.execute(delete(AgentActionDB).where(AgentActionDB.id == aid))
        await db.commit()
        state = await delta_svc.load_state(mid)
        if state:
            state.recovery = None
            await delta_svc.save_state(mid, state)
    await cart_svc.clear_cart(mid, SESSION)
    print("[6] cleaned up (order, action, recovery state, cart)")

    print("\nCART-RECOVERY E2E:", "ALL PASS ✅" if ok else "FAILURES ❌")


if __name__ == "__main__":
    asyncio.run(main())

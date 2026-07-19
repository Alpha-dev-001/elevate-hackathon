"""Demo/test simulation suite.

Drives synthetic customer activity through the **real pipeline** — the same
`record_event` → anomaly detection → `run_decision_cycle` path a real shopper
would — so nothing here is mocked: every decision, role routing, structural
guard, interceptor clamp, and ledger entry is the genuine code path. The only
thing faked is that a human isn't the one browsing.

This is a dev/demo tool (see `scripts/demo_sim.py`), deliberately NOT wired into
the merchant terminal — the product UI carries no demo-only controls. The pure
`build_events` core is unit-tested (test_simulation.py); the async runners are
thin glue over already-tested services.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

# Mirror the anomaly thresholds (behavior_tracker.py) with headroom so a scenario
# fires even for a tiny simulated crowd.
_VELOCITY_MIN_VIEWS = 24   # threshold is ANOMALY_THRESHOLD*4 = 20
_ABANDON_MIN = 6           # threshold is ANOMALY_THRESHOLD = 5
_DWELL_MIN = 3

# The event-driven (reactive) scenarios and which role each is meant to exercise.
SCENARIOS: dict[str, str] = {
    "velocity_spike": "A product goes viral — many fast views → Pricing Strategist (flash sale).",
    "cart_abandon_surge": "Carts abandoned en masse → Sales Rep (recovery offer).",
    "cart_dwell": "Carts left sitting untouched → Sales Rep (dwell nudge).",
}

# The proactive scenarios — no customer events; Qwen looks for a problem itself.
PROACTIVE: dict[str, str] = {
    "review": "Proactive store review — flags high-interest / zero-conversion products.",
    "pricing": "Proactive pricing cycle — reprices a product around its baseline.",
}


def build_events(
    scenario: str, product_ids: list[str], customers: int, target_product_id: str | None = None
) -> list[dict]:
    """Pure: a fanned list of synthetic customer events for one scenario.

    Each event is `{event_type, product_id, session_id, delay}`. The counts are
    floored so the scenario crosses its anomaly threshold even for one customer;
    events fan across at most `customers` sessions. Raises ValueError on an
    unknown scenario or an empty product list. No I/O.

    `target_product_id`, if given and present in `product_ids`, is the product
    that spikes — otherwise defaults to `product_ids[0]` (retakes on the same
    store would otherwise always re-target the same first product).
    """
    if not product_ids:
        raise ValueError("no products to simulate against")
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario!r} (known: {', '.join(SCENARIOS)})")

    if target_product_id and target_product_id in product_ids:
        target = target_product_id
        others = [pid for pid in product_ids if pid != target]
    else:
        target = product_ids[0]
        others = product_ids[1:]
    customers = max(1, customers)
    events: list[dict] = []
    clock = [0.0]

    def add(etype: str, pid: str, sess: int) -> None:
        events.append({
            "event_type": etype,
            "product_id": pid,
            "session_id": f"sim-{sess % customers}",
            "delay": round(clock[0], 2),
        })
        clock[0] += 0.1

    if scenario == "velocity_spike":
        for i in range(max(_VELOCITY_MIN_VIEWS, customers)):
            add("view", target, i)
        # A little background interest on other products for realism — kept well
        # below the target so it stays the single spiking product.
        for j, pid in enumerate(others[:3]):
            add("view", pid, j)
    elif scenario == "cart_abandon_surge":
        for i in range(max(_ABANDON_MIN, customers)):
            add("view", target, i)
            add("cart_add", target, i)
            add("abandon", target, i)
    elif scenario == "cart_dwell":
        for i in range(max(_DWELL_MIN, customers)):
            add("view", target, i)
            add("cart_add", target, i)

    return events


async def run_reactive_scenario(
    slug: str,
    scenario: str,
    customers: int,
    db: "AsyncSession",
    redis: "Redis",
    target_product_id: str | None = None,
) -> dict:
    """Push a scenario's events through the real pipeline, then run the real
    anomaly check + decision cycle (routed to the real role). Returns a summary."""
    from sqlalchemy import select
    from app.models.db_models import MerchantDB, ProductDB
    from app.models.schemas import CustomerEvent, EventType
    from app.services.telemetry import record_event
    from app.services.behavior_tracker import (
        push_event,
        count_abandons_in_window,
        count_views_in_window,
        count_per_product_views_in_window,
        anomaly_description,
    )
    from app.services.decision_engine import run_decision_cycle
    from app.services.qwen_roles import role_for_anomaly

    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise ValueError(f"store not found: {slug}")
    rows = (
        await db.execute(
            select(ProductDB)
            .where(ProductDB.merchant_id == merchant.id)
            .where(ProductDB.is_active == True)  # noqa: E712
        )
    ).scalars().all()
    product_ids = [p.id for p in rows] or ["demo-product"]

    events = build_events(scenario, product_ids, customers, target_product_id)
    now = time.time()
    for ev in events:
        ts = now + ev["delay"]
        await push_event(redis, merchant.id, {
            "event_type": ev["event_type"],
            "product_id": ev["product_id"],
            "session_id": ev["session_id"],
            "timestamp": ts,
        })
        try:
            await record_event(merchant.id, CustomerEvent(
                session_id=ev["session_id"],
                product_id=ev["product_id"],
                event_type=EventType(ev["event_type"]),
                timestamp=int(ts * 1000),
            ))
        except Exception:  # noqa: BLE001 — telemetry mirror is best-effort
            pass

    abandons = await count_abandons_in_window(redis, merchant.id)
    views = await count_views_in_window(redis, merchant.id)
    per_product = await count_per_product_views_in_window(redis, merchant.id)
    desc, spiking_pid = anomaly_description(abandons, views, per_product)

    fired = False
    if desc:
        if spiking_pid:
            prod = await db.get(ProductDB, spiking_pid)
            if prod:
                desc = desc.replace(f"product {spiking_pid}", f'"{prod.name}" ({spiking_pid})')
        await run_decision_cycle(merchant.id, desc, db, redis, role=role_for_anomaly(desc))
        fired = True

    return {
        "scenario": scenario,
        "customers": max(1, customers),
        "events": len(events),
        "anomaly": desc or "(threshold not crossed)",
        "decision_fired": fired,
    }


async def run_proactive(slug: str, kind: str, db: "AsyncSession", redis: "Redis") -> dict:
    """Fire a proactive check — the same one Qwen runs on its schedule — with no
    customer event behind it. `review` = store review (underperformer);
    `pricing` = the dynamic-baseline pricing cycle (store-agnostic tick)."""
    from sqlalchemy import select
    from app.models.db_models import MerchantDB

    if kind == "review":
        merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
        if not merchant:
            raise ValueError(f"store not found: {slug}")
        from app.services.store_review import run_store_review
        action = await run_store_review(merchant.id, db, redis)
        return {"proactive": "store_review", "store": slug, "decision_fired": bool(action)}
    if kind == "pricing":
        from app.services.pricing_cycle import run_pricing_cycle
        actions = await run_pricing_cycle(db, redis)  # runs the whole tick, all stores
        return {"proactive": "pricing_cycle", "decisions_fired": len(actions or [])}
    raise ValueError(f"unknown proactive kind: {kind!r} (known: {', '.join(PROACTIVE)})")

"""
Behavior event ingestion — customer browse events flow in here.
Anomaly detection triggers the decision cycle automatically.
"""
from __future__ import annotations

import asyncio
import time
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_engine
from app.core.redis import get_redis
from app.models.db_models import MerchantDB, ProductDB
from app.services.behavior_tracker import (
    push_event,
    count_abandons_in_window,
    count_views_in_window,
    count_per_product_views_in_window,
    anomaly_description,
)
from app.services.decision_engine import run_decision_cycle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/behavior", tags=["behavior"])


class BehaviorEventIn(BaseModel):
    event_type: str   # view | add_to_cart | abandon | purchase | search
    product_id: str = ""
    session_id: str
    timestamp: float = 0.0  # unix seconds; defaults to now if 0


@router.post("/event/{slug}")
async def ingest_event(
    slug: str,
    event: BehaviorEventIn,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    ts = event.timestamp if event.timestamp > 0 else time.time()
    redis = await get_redis()

    await push_event(redis, merchant.id, {
        "event_type": event.event_type,
        "product_id": event.product_id,
        "session_id": event.session_id,
        "timestamp": ts,
    })

    # Capture merchant_id before the session closes; background task uses a
    # fresh session so it never races with the request session teardown.
    merchant_id = merchant.id

    async def _check():
        abandons = await count_abandons_in_window(redis, merchant_id)
        views = await count_views_in_window(redis, merchant_id)
        per_product = await count_per_product_views_in_window(redis, merchant_id)
        desc, spiking_pid = anomaly_description(abandons, views, per_product)
        if desc:
            async with AsyncSession(get_engine()) as session:
                # Enrich with product name so Qwen sees the human-readable name
                if spiking_pid:
                    product = await session.get(ProductDB, spiking_pid)
                    if product:
                        desc = desc.replace(
                            f"product {spiking_pid}",
                            f'"{product.name}" ({spiking_pid})',
                        )
                await run_decision_cycle(merchant_id, desc, session, redis)

    background.add_task(_check)
    return {"ok": True}


# ─── Simulation ───────────────────────────────────────────────────────────────

# Two demo scenarios so the presenter can show either recovery (abandon surge)
# or a flash sale (velocity spike). Both cross a deterministic anomaly threshold.
ABANDON_SCENARIO = [
    {"event_type": "view",        "product_id": "__first__", "delay": 0.0},
    {"event_type": "view",        "product_id": "__first__", "delay": 0.3},
    {"event_type": "add_to_cart", "product_id": "__first__", "delay": 0.6},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 1.0},
    {"event_type": "view",        "product_id": "__first__", "delay": 1.2},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 1.5},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 1.8},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 2.1},
    {"event_type": "abandon",     "product_id": "__first__", "delay": 2.4},
    {"event_type": "view",        "product_id": "__first__", "delay": 2.7},
]

# Velocity spike: >= ANOMALY_THRESHOLD*4 (default 20) views in the window →
# "products going viral" → Qwen leans toward a flash_sale.
VELOCITY_SCENARIO = [
    {"event_type": "view", "product_id": "__first__", "delay": round(i * 0.1, 2)}
    for i in range(24)
]

SCENARIOS = {
    "cart_abandon_surge": ABANDON_SCENARIO,
    "velocity_spike": VELOCITY_SCENARIO,
}


@router.post("/simulate/{slug}")
async def simulate_activity(
    slug: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    scenario: str = "cart_abandon_surge",
):
    """Fire a pre-scripted event sequence that crosses an anomaly threshold.
    Used by the merchant terminal 'Simulate customer activity' button for the demo.
    scenario=cart_abandon_surge (recovery) | velocity_spike (flash sale).
    """
    DEMO_SCENARIO = SCENARIOS.get(scenario, ABANDON_SCENARIO)
    merchant = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if not merchant:
        raise HTTPException(status_code=404, detail="Store not found")

    # Get first product id for the scenario
    first_product = await db.scalar(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant.id)
        .where(ProductDB.is_active == True)
    )
    product_id = first_product.id if first_product else "demo-product"
    merchant_id = merchant.id

    async def _run_scenario():
        redis = await get_redis()
        now = time.time()
        for i, ev in enumerate(DEMO_SCENARIO):
            event_data = {
                "event_type": ev["event_type"],
                "product_id": product_id,
                "session_id": f"demo-session-{i}",
                "timestamp": now + ev["delay"],
            }
            await push_event(redis, merchant_id, event_data)
            # Also push to telemetry so the product_velocity sorted set and
            # active_sessions match what real customer traffic produces.
            # This keeps the snapshot consistent with the anomaly detection.
            from app.models.schemas import CustomerEvent, EventType
            from app.services.telemetry import record_event
            try:
                evt_type = EventType(ev["event_type"].replace("add_to_cart", "cart_add"))
                await record_event(merchant_id, CustomerEvent(
                    session_id=f"demo-session-{i}",
                    product_id=product_id,
                    event_type=evt_type,
                    timestamp=int((now + ev["delay"]) * 1000),
                ))
            except (ValueError, Exception):
                pass  # non-critical — anomaly detection works from events list
            await asyncio.sleep(0.1)

        # Run anomaly check after scenario completes
        abandons = await count_abandons_in_window(redis, merchant_id)
        views = await count_views_in_window(redis, merchant_id)
        per_product = await count_per_product_views_in_window(redis, merchant_id)
        desc, spiking_pid = anomaly_description(abandons, views, per_product)
        if desc:
            async with AsyncSession(get_engine()) as session:
                # Enrich with product name so Qwen sees the human-readable name
                if spiking_pid:
                    product = await session.get(ProductDB, spiking_pid)
                    if product:
                        desc = desc.replace(
                            f"product {spiking_pid}",
                            f'"{product.name}" ({spiking_pid})',
                        )
                await run_decision_cycle(merchant_id, desc, session, redis)

    background.add_task(_run_scenario)
    return {"ok": True, "scenario": scenario, "events": len(DEMO_SCENARIO)}

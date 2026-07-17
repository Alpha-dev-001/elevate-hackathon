"""
Dynamic baseline pricing — the daily reasoning cycle. A merchant-set
baseline_price stays fixed while Qwen continuously reasons about where the
LIVE price should sit in a bounded range around it, using each product's own
durable history (product_price_history, see pricing_signals.py) and, when a
product is too new to have its own, a borrowed comparable's history.

No price move is ever based on zero data — is_price_rebalance_eligible is the
hard gate: below it, propose_price_rebalance isn't even offered as a tool.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.db_models import ProductDB

logger = logging.getLogger(__name__)

# A comparable must be within this fraction of the new product's baseline
# price to be a meaningful reference point — not a tuned constant, just the
# spec's own "±30%" decision.
COMPARABLE_PRICE_BAND = 0.30


def is_price_rebalance_eligible(history_row_count: int, purchase_count: int) -> bool:
    """Cold-start gate: ≥3 days of product_price_history rows, OR ≥1
    purchase — whichever comes first. Pure — no I/O, easy to test."""
    return history_row_count >= 3 or purchase_count >= 1


def select_comparable_product(
    baseline_price: float, category: str, candidates: list[dict],
) -> str | None:
    """Pure selection over already-fetched candidate summaries (each a dict
    with product_id/category/baseline_price/history_row_count/purchase_count).
    Same category, within ±30% baseline_price, and past ITS OWN cold-start
    threshold (a donor must itself be a proven product). Picks the closest
    baseline_price match. This narrows the field to valid candidates only —
    Qwen decides whether/how to use the comparable's history in the prompt,
    this is not an algorithmic similarity formula beyond that filter."""
    if baseline_price <= 0:
        return None
    valid = [
        c for c in candidates
        if c["category"] == category
        and abs(c["baseline_price"] - baseline_price) / baseline_price <= COMPARABLE_PRICE_BAND
        and is_price_rebalance_eligible(c["history_row_count"], c["purchase_count"])
    ]
    if not valid:
        return None
    return min(valid, key=lambda c: abs(c["baseline_price"] - baseline_price))["product_id"]


async def check_eligibility(product_id: str, db: "AsyncSession") -> bool:
    """I/O wrapper: pulls the two counts is_price_rebalance_eligible needs."""
    from sqlalchemy import select, func
    from app.models.db_models import ProductPriceHistoryDB

    row_count = await db.scalar(
        select(func.count())
        .select_from(ProductPriceHistoryDB)
        .where(ProductPriceHistoryDB.product_id == product_id)
    )
    purchase_sum = await db.scalar(
        select(func.sum(ProductPriceHistoryDB.purchases))
        .where(ProductPriceHistoryDB.product_id == product_id)
    )
    return is_price_rebalance_eligible(int(row_count or 0), int(purchase_sum or 0))


async def find_comparable(product: "ProductDB", db: "AsyncSession") -> str | None:
    """I/O wrapper: fetches same-category active products in this merchant's
    catalog, builds each one's eligibility summary, and delegates the actual
    selection to the pure select_comparable_product."""
    from sqlalchemy import select, func
    from app.models.db_models import ProductDB, ProductPriceHistoryDB

    if not product.category:
        return None

    rows = (
        await db.execute(
            select(ProductDB)
            .where(ProductDB.merchant_id == product.merchant_id)
            .where(ProductDB.id != product.id)
            .where(ProductDB.is_active == True)
            .where(ProductDB.category == product.category)
        )
    ).scalars().all()

    candidates: list[dict] = []
    for c in rows:
        row_count = await db.scalar(
            select(func.count())
            .select_from(ProductPriceHistoryDB)
            .where(ProductPriceHistoryDB.product_id == c.id)
        )
        purchase_sum = await db.scalar(
            select(func.sum(ProductPriceHistoryDB.purchases))
            .where(ProductPriceHistoryDB.product_id == c.id)
        )
        candidates.append({
            "product_id": c.id, "category": c.category,
            "baseline_price": c.baseline_price,
            "history_row_count": int(row_count or 0),
            "purchase_count": int(purchase_sum or 0),
        })

    return select_comparable_product(product.baseline_price, product.category, candidates)


def format_history_summary(rows: list[dict]) -> str:
    """rows: [{"date","views","cart_adds","purchases","price_active",
    "signal_quality"}, ...]. Suspect-flagged days are excluded — Qwen
    reasons over fewer, trusted data points rather than a "corrected"
    number (see pricing_signals.flag_suspicious_signals)."""
    trusted = [r for r in rows if r.get("signal_quality") != "suspect"]
    if not trusted:
        return "no trusted history yet"
    return "; ".join(
        f"{r['date']}: {r['views']} views, {r['cart_adds']} cart-adds, "
        f"{r['purchases']} purchases at ${r['price_active']:.2f}"
        for r in trusted
    )


def compute_magnitude(action_type: str, payload: dict, baseline_price: float | None) -> float | None:
    """The 'how far' number to compare across differently-shaped actions:
    discount_percent for discount-bearing types, or the % move from
    baseline_price for price_rebalance. None if the shape doesn't match."""
    if action_type == "price_rebalance":
        if baseline_price and baseline_price > 0 and "new_price" in payload:
            return abs((payload["new_price"] - baseline_price) / baseline_price * 100)
        return None
    if "discount_percent" in payload:
        return float(payload["discount_percent"])
    return None


def build_revealed_preference_summary(actions: list[dict]) -> str:
    """actions: [{"action_type","status","payload"}, ...] for one merchant,
    trailing window already applied by the caller. status == 'executed' is
    the approved bucket, 'dismissed' is the dismissed bucket — see this
    task's docstring-level note on why AgentActionDB.status stands in for a
    joined outcome-positive flag. Returns "" when there's not enough data."""
    approved, dismissed = [], []
    for a in actions:
        mag = compute_magnitude(a["action_type"], a.get("payload", {}), a.get("baseline_price"))
        if mag is None:
            continue
        if a["status"] == "executed":
            approved.append(mag)
        elif a["status"] == "dismissed":
            dismissed.append(mag)

    if not approved and not dismissed:
        return ""
    parts = []
    if approved:
        parts.append(f"approved moves up to {max(approved):.0f}%")
    if dismissed:
        parts.append(f"dismissed a proposed {min(dismissed):.0f}% move")
    return "this merchant has " + " and ".join(parts) + "."


PRICING_PROMPT = """You are the autonomous pricing brain for "{store_name}".
Brand mood: {mood} | Voice: {brand_voice}

Product under review: {product_name} — baseline price ${baseline_price:.2f}, \
current live price ${current_price:.2f}, unit cost ${cost_price:.2f}.
Recent history (last 7 days): {history_summary}
{comparable_block}{memory_block}
Reason step by step about whether the live price should move, and if so to
where, within your authorized range around the baseline. Call the
propose_price_rebalance tool to act, or make no tool call at all if the
current price is already right. Include your reasoning in your message —
cite the specific signals driving your call.

Never propose a price for a product with no history and no valid comparable —
if you have no real data to reason from, do not call the tool."""


def compose_pricing_prompt(
    *,
    store_name: str,
    mood: str,
    brand_voice: str,
    product_name: str,
    baseline_price: float,
    current_price: float,
    cost_price: float,
    history_summary: str,
    comparable_summary: str = "",
    memory_context: str = "",
) -> str:
    """Pure — no I/O, mirrors compose_decision_prompt's shape exactly."""
    comparable_block = (
        f"\nA similar product's recent performance, for reference since this "
        f"product is new: {comparable_summary}\n"
        if comparable_summary else ""
    )
    memory_block = (
        f"\nPrior outcomes for this store (learn from them): {memory_context}\n"
        if memory_context else ""
    )
    return PRICING_PROMPT.format(
        store_name=store_name, mood=mood, brand_voice=brand_voice,
        product_name=product_name, baseline_price=baseline_price,
        current_price=current_price, cost_price=cost_price,
        history_summary=history_summary,
        comparable_block=comparable_block, memory_block=memory_block,
    )


import os
import time as _time
from app.core.redis import Keys

# Env-configurable, same pattern as ANOMALY_THRESHOLD (behavior_tracker.py).
PRICE_REVIEW_INTERVAL_SECONDS = int(os.getenv("PRICE_REVIEW_INTERVAL_SECONDS", "86400"))  # daily
PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS = int(os.getenv("PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS", "3600"))  # hourly
PRICE_REVIEW_ESCALATION_DECAY_TICKS = 3
PRICING_TICK_INTERVAL_SECONDS = int(os.getenv("PRICING_TICK_INTERVAL_SECONDS", "3600"))


def next_check_decision(current_streak: int, escalated_this_tick: bool) -> tuple[int, int]:
    """Pure — no I/O. Returns (new_escalation_streak, next_interval_seconds).
    A fresh anomaly this tick always escalates to hourly and (re)starts the
    decay streak at 1; otherwise an active streak counts up toward
    PRICE_REVIEW_ESCALATION_DECAY_TICKS quiet ticks before reverting to
    daily; no active streak stays daily. A literal continuous half-life
    function was considered and rejected — this step-based version produces
    the same practical behavior with far less machinery."""
    if escalated_this_tick:
        return 1, PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS
    if current_streak <= 0:
        return 0, PRICE_REVIEW_INTERVAL_SECONDS
    new_streak = current_streak + 1
    if new_streak >= PRICE_REVIEW_ESCALATION_DECAY_TICKS:
        return 0, PRICE_REVIEW_INTERVAL_SECONDS
    return new_streak, PRICE_REVIEW_ESCALATED_INTERVAL_SECONDS


async def should_run_pricing_check(product_id: str, redis) -> bool:
    """No stored next-check time == never checked before == due now."""
    raw = await redis.get(Keys.next_price_check(product_id))
    if raw is None:
        return True
    return int(_time.time() * 1000) >= int(raw)


async def record_pricing_check_result(product_id: str, redis, *, escalated_this_tick: bool) -> None:
    raw_streak = await redis.get(Keys.price_check_escalation(product_id))
    current_streak = int(raw_streak) if raw_streak else 0
    new_streak, interval_seconds = next_check_decision(current_streak, escalated_this_tick)
    now = int(_time.time() * 1000)
    await redis.set(Keys.next_price_check(product_id), now + interval_seconds * 1000)
    if new_streak > 0:
        await redis.set(Keys.price_check_escalation(product_id), new_streak)
    else:
        await redis.delete(Keys.price_check_escalation(product_id))


async def run_pricing_cycle(db: "AsyncSession", redis) -> list:
    """One pass per live merchant, per eligible-and-due product. Per-product
    (and per-merchant) try/except — one bad product/merchant must never skip
    the rest, same discipline as store_review.py's tick. Returns the list of
    AgentAction results actually fired this pass (gated ones and
    auto-trusted ones both included — run_decision_cycle returns either)."""
    from sqlalchemy import select
    from app.models.db_models import MerchantDB, ProductDB, BrandProfileDB, ProductPriceHistoryDB, AgentActionDB
    from app.services.decision_engine import run_decision_cycle
    from app.services.tools import DECISION_TOOLS
    from app.services import behavior_tracker
    from app.services.memory import get_memory, build_memory_context

    price_rebalance_tools = [
        t for t in DECISION_TOOLS if t["function"]["name"] == "propose_price_rebalance"
    ]
    actions = []

    merchants = (
        await db.execute(select(MerchantDB).where(MerchantDB.is_live == True))
    ).scalars().all()

    for merchant in merchants:
        try:
            brand_profile = await db.get(BrandProfileDB, merchant.id)
            brand_voice, mood = "professional, friendly", "balanced"
            if brand_profile:
                gb = brand_profile.generated_brand or {}
                brand_voice = gb.get("brand", {}).get("brand_voice_profile", brand_voice)
                mood = gb.get("brand", {}).get("layout_variant", mood)

            products = (
                await db.execute(
                    select(ProductDB)
                    .where(ProductDB.merchant_id == merchant.id)
                    .where(ProductDB.is_active == True)
                )
            ).scalars().all()

            per_product_views = await behavior_tracker.count_per_product_views_in_window(
                redis, merchant.id
            )

            for product in products:
                try:
                    if not await should_run_pricing_check(product.id, redis):
                        continue

                    # Eligibility is "own data clears the threshold" OR "a valid
                    # comparable exists" — NOT own-data-only. A brand-new product
                    # with zero history must still reach the borrow-from-comparable
                    # path (spec: "How does a new product get priced before it has
                    # its own history? Borrow from a similar, proven product").
                    # Checking check_eligibility() alone and skipping on False would
                    # make that path unreachable — comparable lookup must run first
                    # for a not-yet-eligible product, not be skipped alongside it.
                    own_eligible = await check_eligibility(product.id, db)
                    comparable_pid = await find_comparable(product, db) if not own_eligible else None
                    if not own_eligible and not comparable_pid:
                        continue  # no data, no valid comparable — stays at baseline (cold-start gate)

                    def _rows_to_dicts(rows):
                        return [
                            {"date": r.date, "views": r.views, "cart_adds": r.cart_adds,
                             "purchases": r.purchases, "price_active": r.price_active,
                             "signal_quality": r.signal_quality}
                            for r in reversed(rows)
                        ]

                    history_rows = (
                        await db.execute(
                            select(ProductPriceHistoryDB)
                            .where(ProductPriceHistoryDB.product_id == product.id)
                            .order_by(ProductPriceHistoryDB.date.desc())
                            .limit(7)
                        )
                    ).scalars().all()
                    history_summary = format_history_summary(_rows_to_dicts(history_rows))

                    comparable_summary = ""
                    if comparable_pid:
                        comp_rows = (
                            await db.execute(
                                select(ProductPriceHistoryDB)
                                .where(ProductPriceHistoryDB.product_id == comparable_pid)
                                .order_by(ProductPriceHistoryDB.date.desc())
                                .limit(7)
                            )
                        ).scalars().all()
                        comparable_summary = format_history_summary(_rows_to_dicts(comp_rows))

                    recent_actions = (
                        await db.execute(
                            select(AgentActionDB)
                            .where(AgentActionDB.merchant_id == merchant.id)
                            .where(AgentActionDB.action_type.in_(
                                ["price_rebalance", "flash_sale", "scarcity_price"]
                            ))
                            .where(AgentActionDB.status.in_(["executed", "dismissed"]))
                            .order_by(AgentActionDB.created_at.desc())
                            .limit(20)
                        )
                    ).scalars().all()
                    # recent_actions is merchant-wide (spec: the revealed-preference
                    # aggregate is "computed from AgentActionDB rows... for a
                    # merchant", not scoped to the one product under review), so a
                    # price_rebalance row's magnitude needs ITS OWN product's
                    # baseline_price, not this loop's current `product` — resolved
                    # from the `products` list already fetched above, zero extra query.
                    product_baseline_by_id = {p.id: p.baseline_price for p in products}
                    revealed_pref = build_revealed_preference_summary([
                        {
                            "action_type": a.action_type, "status": a.status,
                            "payload": a.payload or {},
                            "baseline_price": product_baseline_by_id.get(
                                (a.payload or {}).get("product_id")
                            ),
                        }
                        for a in recent_actions
                    ])

                    memory_entries = await get_memory(merchant.id, db, redis)
                    memory_context = build_memory_context(memory_entries)
                    combined_memory = "; ".join(filter(None, [revealed_pref, memory_context]))

                    prompt = compose_pricing_prompt(
                        store_name=merchant.store_name, mood=mood, brand_voice=brand_voice,
                        product_name=product.name, baseline_price=product.baseline_price,
                        current_price=product.price, cost_price=product.cost_price,
                        history_summary=history_summary, comparable_summary=comparable_summary,
                        memory_context=combined_memory,
                    )

                    escalated_this_tick = (
                        per_product_views.get(product.id, 0) >= behavior_tracker.ANOMALY_THRESHOLD * 4
                    )

                    action = await run_decision_cycle(
                        merchant.id, f"Price review: {product.name}", db, redis,
                        tools=price_rebalance_tools, target_product_id=product.id,
                        prompt_override=prompt,
                    )
                    if action:
                        actions.append(action)
                        if comparable_pid:
                            # Tag the row so Task 14's reversion check can tell a
                            # comparable-informed move apart from an own-data move —
                            # only the former reverts on engagement-without-conversion,
                            # per the spec's reversion rule. run_decision_cycle has no
                            # kwarg for this (it doesn't know about comparables at
                            # all), so it's set here, directly on the just-created row.
                            row = await db.get(AgentActionDB, action.id)
                            if row:
                                row.payload = {**(row.payload or {}), "comparable_informed": True}
                                await db.commit()

                    await record_pricing_check_result(
                        product.id, redis, escalated_this_tick=escalated_this_tick,
                    )
                except Exception as e:  # noqa: BLE001 — one product's failure must not skip the rest
                    logger.warning(
                        "[pricing_cycle] check failed for product %s: %s", product.id, e,
                    )
        except Exception as e:  # noqa: BLE001 — one merchant's failure must not skip the rest
            logger.warning("[pricing_cycle] cycle failed for merchant %s: %s", merchant.id, e)

    return actions


def should_revert(views_after: int, cart_adds_after: int, purchases_after: int) -> bool:
    """Engagement without conversion — the reversion trigger over a completed
    3-day post-move window. 'Engagement' means at least some views or
    cart-adds happened; 'without conversion' means zero purchases. A window
    with nothing happening at all is just low traffic, a distinct signal
    from 'click but no buy' (spec: 'meaningful specifically')."""
    return (views_after > 0 or cart_adds_after > 0) and purchases_after == 0


def compute_reversion_price(current_price: float, baseline_price: float) -> float:
    """Steps the live price halfway back toward baseline_price — a simple,
    explicit halving step, not a tuned decay constant."""
    gap = baseline_price - current_price
    return round(current_price + gap / 2, 2)


async def check_reversion_triggers(db: "AsyncSession", redis) -> int:
    """Run once per tick, BEFORE apply_reversions. For each comparable-
    informed PRICE_REBALANCE move whose 3-day post-move window has just
    completed, decide whether to START reverting. Each move is checked at
    most once ever — payload["reversion_checked"] is set immediately so a
    move already evaluated (whichever way it went) is never re-evaluated,
    which is what keeps this from re-triggering on the same static window
    every subsequent tick. Returns the number of products newly added to
    the reverting set this call."""
    from sqlalchemy import select
    from datetime import datetime, timezone
    from app.models.db_models import AgentActionDB, ProductPriceHistoryDB
    from app.core.redis import Keys

    started = 0
    candidates = (
        await db.execute(
            select(AgentActionDB)
            .where(AgentActionDB.action_type == "price_rebalance")
            .where(AgentActionDB.status == "executed")
        )
    ).scalars().all()

    for action in candidates:
        payload = action.payload or {}
        if not payload.get("comparable_informed") or payload.get("reversion_checked"):
            continue
        if not action.executed_at:
            continue
        try:
            move_date = datetime.fromtimestamp(
                action.executed_at / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")
            product_id = payload.get("product_id", "")
            window_rows = (
                await db.execute(
                    select(ProductPriceHistoryDB)
                    .where(ProductPriceHistoryDB.product_id == product_id)
                    .where(ProductPriceHistoryDB.date > move_date)
                    .order_by(ProductPriceHistoryDB.date.asc())
                    .limit(3)
                )
            ).scalars().all()
            if len(window_rows) < 3:
                continue  # window not complete yet — check again next tick, don't mark checked

            views_after = sum(r.views for r in window_rows)
            cart_adds_after = sum(r.cart_adds for r in window_rows)
            purchases_after = sum(r.purchases for r in window_rows)

            action.payload = {**payload, "reversion_checked": True}
            if should_revert(views_after, cart_adds_after, purchases_after):
                await redis.sadd(Keys.reverting_products(), product_id)
                started += 1
        except Exception as e:  # noqa: BLE001 — one action's failure must not skip the rest
            logger.warning(
                "[pricing_cycle] reversion trigger check failed for action %s: %s", action.id, e,
            )

    await db.commit()
    return started


async def apply_reversions(db: "AsyncSession", redis) -> int:
    """Run once per tick, after check_reversion_triggers. For every product
    currently in the reverting set: stop (remove from the set) if the most
    recent rolled-up day shows a purchase, or if the price has already
    reached baseline; otherwise apply one more halving step. Per-product
    try/except."""
    from sqlalchemy import select
    from app.models.db_models import ProductDB, ProductPriceHistoryDB
    from app.core.redis import Keys

    reverted = 0
    active_pids = await redis.smembers(Keys.reverting_products())

    for product_id in active_pids:
        try:
            product = await db.get(ProductDB, product_id)
            if not product or not product.is_active:
                await redis.srem(Keys.reverting_products(), product_id)
                continue

            latest_row = await db.scalar(
                select(ProductPriceHistoryDB)
                .where(ProductPriceHistoryDB.product_id == product_id)
                .order_by(ProductPriceHistoryDB.date.desc())
            )
            if latest_row and latest_row.purchases > 0:
                # A purchase occurred — stop reverting, reasoning restarts from real data.
                await redis.srem(Keys.reverting_products(), product_id)
                continue

            if abs(product.price - product.baseline_price) < 0.01:
                await redis.srem(Keys.reverting_products(), product_id)
                continue

            product.price = compute_reversion_price(product.price, product.baseline_price)
            await db.flush()
            from app.routers.products import _sync_state_if_live
            await _sync_state_if_live(db, product.merchant_id)
            reverted += 1
        except Exception as e:  # noqa: BLE001 — one product's failure must not skip the rest
            logger.warning("[pricing_cycle] reversion step failed for product %s: %s", product_id, e)

    await db.commit()
    return reverted


async def evaluate_trust_outcomes(db: "AsyncSession", redis) -> int:
    """Run once per tick, alongside check_reversion_triggers. Updates the
    graduated-autonomy trust streak (Task 11) for each executed PRICE_REBALANCE
    action from REAL post-move purchase data, once a full 3-day
    product_price_history window exists after the move.

    This does NOT run through outcome_observer.observe_outcome/
    schedule_observation — that mechanism fires ~agent_action_duration_minutes
    (default 30 min) after approval and measures outcome via
    OrderDB.promo_applied == action.promo_id. A direct price change never
    registers a Promo/RecoveryOffer, so that count is structurally always 0
    for this action type — the trust streak could never advance, silently
    defeating graduated autonomy end to end (found in final whole-branch
    review). Even swapping the data source there wouldn't help: 30 minutes
    after approval, rollup_daily_signals (a once-a-day job) has not yet
    written a single new product_price_history row, so there would be
    nothing real to check. The trust outcome genuinely only becomes knowable
    on the same multi-day cadence this daily tick already runs on — so it is
    evaluated here instead, using the identical "N-day window after
    executed_at" pattern check_reversion_triggers already established, and a
    one-time payload["trust_evaluated"] marker for the same reason
    check_reversion_triggers uses payload["reversion_checked"]: re-running the
    same static window's purchase count on every subsequent tick must not
    re-score (and re-mutate the streak for) the same move twice.

    Covers BOTH the merchant-approved and the auto-trusted execution path
    (Task 12) — both end in status="executed" with executed_at set, so an
    auto-applied move's outcome is evaluated here too, closing the gap where
    it previously fed neither memory nor the trust streak at all."""
    from sqlalchemy import select
    from datetime import datetime, timezone
    from app.models.db_models import AgentActionDB, ProductPriceHistoryDB
    from app.services.autopilot_trust import update_trust_streak

    evaluated = 0
    candidates = (
        await db.execute(
            select(AgentActionDB)
            .where(AgentActionDB.action_type == "price_rebalance")
            .where(AgentActionDB.status == "executed")
        )
    ).scalars().all()

    for action in candidates:
        payload = action.payload or {}
        if payload.get("trust_evaluated") or not action.executed_at:
            continue
        try:
            product_id = payload.get("product_id", "")
            if not product_id:
                continue
            move_date = datetime.fromtimestamp(
                action.executed_at / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d")
            window_rows = (
                await db.execute(
                    select(ProductPriceHistoryDB)
                    .where(ProductPriceHistoryDB.product_id == product_id)
                    .where(ProductPriceHistoryDB.date > move_date)
                    .order_by(ProductPriceHistoryDB.date.asc())
                    .limit(3)
                )
            ).scalars().all()
            if len(window_rows) < 3:
                continue  # window not complete yet — evaluate again next tick

            purchases = sum(r.purchases for r in window_rows)
            action.payload = {**payload, "trust_evaluated": True}
            approved = action.merchant_behavior != "dismissed"
            outcome_negative = purchases == 0
            await update_trust_streak(
                action.merchant_id, product_id, "price_rebalance", db,
                approved=approved, outcome_negative=outcome_negative,
            )
            evaluated += 1
        except Exception as e:  # noqa: BLE001 — one action's failure must not skip the rest
            logger.warning(
                "[pricing_cycle] trust evaluation failed for action %s: %s", action.id, e,
            )

    await db.commit()
    return evaluated


def start_pricing_background_loop() -> None:
    """Same in-process asyncio loop shape as store_review.py's
    start_background_loop. The outer loop ticks hourly
    (PRICING_TICK_INTERVAL_SECONDS) so an escalated product can actually get
    an hourly check; should_run_pricing_check is what gates each PRODUCT to
    its own daily-vs-escalated cadence within that shared outer rhythm."""
    import asyncio
    from app.core.redis import get_redis

    async def _tick():
        from app.core.database import get_session_factory
        factory = get_session_factory()
        try:
            async with factory() as db:
                redis = await get_redis()
                # Rollup runs FIRST — everything downstream (eligibility,
                # reversion windows, trust evaluation) reads product_price_history,
                # which only this call ever writes. Gated to once per UTC day
                # internally; safe to call every tick.
                from app.services.pricing_signals import run_daily_rollup_if_due
                rolled_up = await run_daily_rollup_if_due(db, redis)
                if rolled_up:
                    logger.info("[pricing_cycle] daily rollup wrote %d row(s)", rolled_up)
                # Reversion runs BEFORE fresh proposals so a reverted price is
                # what run_pricing_cycle reasons over this same tick, not stale.
                await check_reversion_triggers(db, redis)
                await apply_reversions(db, redis)
                # Trust-streak evaluation also runs on this same daily cadence
                # (see evaluate_trust_outcomes' docstring for why it can't run
                # on outcome_observer's 30-minute schedule_observation timer).
                await evaluate_trust_outcomes(db, redis)
                actions = await run_pricing_cycle(db, redis)
                if actions:
                    logger.info("[pricing_cycle] %d pricing action(s) this tick", len(actions))
        except Exception as e:  # noqa: BLE001 — a failed tick must not kill the loop
            logger.warning("[pricing_cycle] tick failed: %s", e)

    async def _runner():
        while True:
            await asyncio.sleep(PRICING_TICK_INTERVAL_SECONDS)
            await _tick()

    asyncio.create_task(_runner())
    logger.info(
        "[pricing_cycle] background loop started (every %ss)", PRICING_TICK_INTERVAL_SECONDS,
    )

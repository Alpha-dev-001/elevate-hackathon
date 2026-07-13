"""
Qwen decision engine — reads store state + behavior anomaly, fires one action.
Called when behavior_tracker detects an anomaly threshold crossing.
"""
from __future__ import annotations

import json
import logging
import secrets
import time
from uuid import uuid4
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import AgentAction, AgentActionStatus, AgentActionType, WSEventType
from app.models.db_models import AgentActionDB, MerchantDB, BrandProfileDB, ProductDB
from app.services.brand import _qwen_chat, _extract_json, BrandGenerationError
from app.services.tools import DECISION_TOOLS, TOOL_TO_ACTION_TYPE, narrative_from_tool, parse_tool_args
from app.core.ws_manager import manager
from app.core.config import get_settings

logger = logging.getLogger(__name__)

DECISION_PROMPT = """You are the autonomous commerce brain for "{store_name}".
Brand mood: {mood} | Voice: {brand_voice}
Brand rules (never violate): {brand_rules_summary}

Current products: {products_summary}
Behavior anomaly: {anomaly_description}
{memory_block}
Use the available tools to propose ONE action for the merchant to review.
Include your step-by-step reasoning in your message — explain what you observed,
why this action makes sense, and what outcome you expect (be specific with numbers).

A recovery_offer is an ORDER-LEVEL percentage discount on the shopper's existing
cart to win back an abandoned checkout — this store has no shipping concept, so
never propose free shipping.

The merchant approves before execution. Make it compelling."""


def _extract_count(anomaly_desc: str) -> int:
    """The anomaly magnitude captured at trigger time (e.g. '5 abandons', '24
    views') — the honest basis for a revenue estimate. 0 if none found."""
    import re
    m = re.search(r"\d+", anomaly_desc or "")
    return int(m.group()) if m else 0


def grounded_gmv(action_type: str, anomaly_count: int, avg_price: float) -> float:
    """A revenue-impact estimate tied to REAL signals instead of a Qwen guess:
    the anomaly magnitude × the catalog's average price × a tunable per-type rate.
    Returns 0.0 when we can't ground it (caller then falls back to Qwen's number)."""
    if avg_price <= 0 or anomaly_count <= 0:
        return 0.0
    s = get_settings()
    rate = s.recovery_gmv_rate if action_type == "recovery_offer" else s.flash_gmv_rate
    return round(anomaly_count * avg_price * rate, 2)


def compose_decision_prompt(
    *,
    store_name: str,
    mood: str,
    brand_voice: str,
    brand_rules_summary: str,
    products_summary: str,
    anomaly_description: str,
    memory_context: str = "",
) -> str:
    """Build the decision prompt, injecting prior-outcome memory when present.

    Extracted (and pure) so the memory-injection behavior is unit-testable
    without a DB, Redis, or a live Qwen call.
    """
    memory_block = f"\nPrior outcomes for this store (learn from them):\n{memory_context}\n" if memory_context else ""
    return DECISION_PROMPT.format(
        store_name=store_name,
        mood=mood,
        brand_voice=brand_voice,
        brand_rules_summary=brand_rules_summary,
        products_summary=products_summary,
        anomaly_description=anomaly_description,
        memory_block=memory_block,
    )


async def run_decision_cycle(
    merchant_id: str,
    anomaly_desc: str,
    db: "AsyncSession",
    redis: "Redis",
) -> AgentAction | None:
    """Run a full Qwen decision cycle and persist + broadcast the result.

    Returns the created AgentAction or None if:
    - there is already a pending action (one at a time, unless it's stale)
    - Qwen returns garbage we can't trust
    """
    from sqlalchemy import select

    # Gate: only one pending action at a time per store.
    # If the existing pending action is older than the TTL, the signal is stale —
    # auto-dismiss it so new anomalies can trigger fresh decisions.
    existing = await db.scalar(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant_id)
        .where(AgentActionDB.status == "pending")
    )
    if existing:
        ttl = get_settings().pending_action_ttl_seconds
        age_seconds = (int(time.time() * 1000) - existing.created_at) / 1000
        if age_seconds > ttl:
            existing.status = "dismissed"
            await db.commit()
            logger.info(
                "[decision] auto-dismissed stale action %s (age: %.0fs, ttl: %ds) for %s",
                existing.id, age_seconds, ttl, merchant_id,
            )
            # Notify terminal so the stale card is removed immediately
            from app.models.schemas import WSMessage
            await manager.push_to_terminal(
                merchant_id,
                WSMessage(
                    event=WSEventType.ACTION_EXPIRED,
                    payload={"action_id": existing.id, "reason": "signal_stale"},
                    merchant_id=merchant_id,
                    timestamp=int(time.time() * 1000),
                ),
            )
        else:
            logger.info(f"[decision] skipping cycle — pending action already exists for {merchant_id}")
            return None

    merchant = await db.get(MerchantDB, merchant_id)
    if not merchant:
        return None

    brand_profile = await db.get(BrandProfileDB, merchant_id)
    brand_voice = "professional, friendly"
    mood = "balanced"
    brand_rules_summary = "maintain brand integrity"
    if brand_profile:
        gb = brand_profile.generated_brand or {}
        brand_voice = gb.get("brand", {}).get("brand_voice_profile", brand_voice)
        mood = gb.get("brand", {}).get("layout_variant", mood)
        guards = gb.get("guards", {})
        rules = guards.get("rules", [])
        brand_rules_summary = "; ".join(r.get("description", "") for r in rules[:3]) or brand_rules_summary

    products_result = await db.execute(
        select(ProductDB)
        .where(ProductDB.merchant_id == merchant_id)
        .where(ProductDB.is_active == True)
        .limit(10)
    )
    products = products_result.scalars().all()
    products_summary = ", ".join(
        f"{p.name} (${p.price}, stock: {p.stock})" for p in products
    ) or "no products yet"

    # Catalog-wide average price (not just the 10-row prompt sample) — the honest
    # basis for the grounded revenue estimate below.
    from sqlalchemy import func
    avg_price = float(await db.scalar(
        select(func.avg(ProductDB.price))
        .where(ProductDB.merchant_id == merchant_id)
        .where(ProductDB.is_active == True)
        .where(ProductDB.price > 0)
    ) or 0.0)

    # Pull prior-outcome memory and inject it — the cognitive loop closes here.
    from app.services.memory import get_memory, build_memory_context
    try:
        entries = await get_memory(merchant_id, db, redis)
    except Exception as e:  # noqa: BLE001 — memory must never block a decision
        logger.warning("[decision] memory read failed for %s: %s", merchant_id, e)
        entries = []
    memory_context = build_memory_context(entries)

    prompt = compose_decision_prompt(
        store_name=merchant.store_name,
        mood=mood,
        brand_voice=brand_voice,
        brand_rules_summary=brand_rules_summary,
        products_summary=products_summary,
        anomaly_description=anomaly_desc,
        memory_context=memory_context,
    )
    estimated_tokens = len(prompt) // 4  # rough char/4 heuristic for the terminal badge

    try:
        message = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.5,
            timeout=45.0,
            tools=DECISION_TOOLS,
            tool_choice="auto",
            merchant_id=merchant_id,
            step="decision_cycle",
        )
    except BrandGenerationError as e:
        logger.error(f"[decision] Qwen failed for {merchant_id}: {e}")
        return None

    # --- Parse tool-calling response ---
    if not isinstance(message, dict):
        logger.error("[decision] unexpected response type from _qwen_chat (tools mode)")
        return None

    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        # Qwen declined to propose an action (no anomaly worth acting on)
        logger.info(f"[decision] Qwen declined to call a tool for {merchant_id}")
        return None

    # Take the first tool call (we asked for ONE action)
    tc = tool_calls[0]
    tool_name = tc.get("function", {}).get("name", "")
    tool_args = parse_tool_args(tc.get("function", {}).get("arguments", "{}"))

    if not tool_name:
        logger.warning("[decision] tool call missing function name")
        return None

    # Map tool name → AgentActionType enum
    action_type_enum = TOOL_TO_ACTION_TYPE.get(tool_name)
    if action_type_enum is None:
        logger.warning(f"[decision] unknown tool '{tool_name}', defaulting to flash_sale")
        action_type_enum = AgentActionType.FLASH_SALE

    # Qwen's reasoning comes from the message content (alongside tool_calls)
    reasoning = (message.get("content") or "")[:1000]

    # Narrative fields templated from tool call + context
    # Use the product Qwen actually targeted, not just the first in the list
    # propose_duplicate_merge uses keep_product_id, not product_id — same
    # fallback purpose (which product's name goes in the option card title).
    targeted_pid = tool_args.get("product_id") or tool_args.get("keep_product_id")
    targeted_product_name = None
    if targeted_pid:
        for p in products:
            if p.id == targeted_pid:
                targeted_product_name = p.name
                break
    product_name_for_narrative = targeted_product_name or (products[0].name if products else None)
    narrative = narrative_from_tool(
        tool_name, tool_args, product_name_for_narrative, anomaly_desc, brand_voice
    )

    promo_id = f"ELEV_{merchant_id[:4].upper()}_{secrets.token_hex(3).upper()}"
    now = int(time.time() * 1000)

    # Ground the revenue estimate in the real anomaly magnitude + catalog price
    anomaly_count = _extract_count(anomaly_desc)
    est_gmv = grounded_gmv(action_type_enum.value, anomaly_count, avg_price)
    if est_gmv <= 0:
        est_gmv = float(tool_args.get("estimated_gmv", 0) or 0)

    action_db = AgentActionDB(
        id=str(uuid4()),
        merchant_id=merchant_id,
        promo_id=promo_id,
        action_type=action_type_enum.value,
        trigger=narrative["trigger"],
        reasoning=reasoning,
        title=narrative["title"][:200],
        description=narrative["description"][:500],
        estimated_gmv=est_gmv,
        estimated_confidence=0.75,  # tool calling = high confidence in structured output
        payload=tool_args,  # tool args become the execution payload directly
        brand_check=narrative["brand_check"][:500],
        status="pending",
        created_at=now,
        trigger_description=anomaly_desc[:1000],
    )
    db.add(action_db)
    await db.commit()
    await db.refresh(action_db)

    action = AgentAction(
        id=action_db.id,
        merchant_id=action_db.merchant_id,
        promo_id=action_db.promo_id,
        action_type=AgentActionType(action_db.action_type),
        trigger=action_db.trigger,
        title=action_db.title,
        description=action_db.description,
        estimated_gmv=action_db.estimated_gmv,
        estimated_confidence=action_db.estimated_confidence,
        payload=action_db.payload,
        brand_check=action_db.brand_check,
        status=AgentActionStatus(action_db.status),
        created_at=action_db.created_at,
    )

    # Push to merchant terminal via WebSocket — include real cost data
    from app.models.schemas import WSMessage
    usage_summary = {}
    try:
        from app.services.brand import get_usage_summary
        usage_summary = await get_usage_summary(merchant_id)
    except Exception:
        pass  # cost tracking must never block the decision push

    await manager.push_to_terminal(
        merchant_id,
        WSMessage(
            event=WSEventType.AGENT_ACTION,
            payload={
                "action": action.model_dump(),
                "estimated_tokens": estimated_tokens,
                "memory_count": len(entries),
                "usage": usage_summary,
            },
            merchant_id=merchant_id,
            timestamp=now,
        ),
    )

    logger.info(f"[decision] fired {action.action_type} action {action.id} for {merchant_id}")
    return action

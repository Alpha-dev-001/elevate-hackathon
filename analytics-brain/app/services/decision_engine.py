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
from app.core.ws_manager import manager
from app.core.config import get_settings

logger = logging.getLogger(__name__)

DECISION_PROMPT = """You are the autonomous commerce brain for "{store_name}".
Brand mood: {mood} | Voice: {brand_voice}
Brand rules (never violate): {brand_rules_summary}

Current products: {products_summary}
Behavior anomaly: {anomaly_description}

Decide ONE action. Return ONLY this JSON:
{{
  "action_type": "<flash_sale|layout_morph|scarcity_price|recovery_offer|copy_rewrite>",
  "trigger": "<1 sentence: what caused this>",
  "title": "<merchant-facing card title, max 8 words>",
  "description": "<merchant-facing description, max 20 words>",
  "estimated_gmv": <estimated revenue impact as number>,
  "estimated_confidence": <0.0-1.0>,
  "payload": {{
    "flash_sale fields if action_type=flash_sale": {{
      "discount_percent": 15,
      "duration_minutes": 30,
      "target": "best_seller"
    }},
    "layout_morph fields if action_type=layout_morph": {{
      "new_grid": "2col-featured",
      "reason": "highlight trending product"
    }},
    "recovery_offer fields if action_type=recovery_offer": {{
      "offer": "free_shipping",
      "message": "Come back — we saved your cart"
    }}
  }},
  "brand_check": "<confirm this respects brand rules or flag conflict>"
}}

The merchant approves before execution. Make it compelling.
Return ONLY JSON."""


async def run_decision_cycle(
    merchant_id: str,
    anomaly_desc: str,
    db: "AsyncSession",
    redis: "Redis",
) -> AgentAction | None:
    """Run a full Qwen decision cycle and persist + broadcast the result.

    Returns the created AgentAction or None if:
    - there is already a pending action (one at a time)
    - Qwen returns garbage we can't trust
    """
    from sqlalchemy import select

    # Gate: only one pending action at a time per store
    existing = await db.scalar(
        select(AgentActionDB)
        .where(AgentActionDB.merchant_id == merchant_id)
        .where(AgentActionDB.status == "pending")
    )
    if existing:
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

    prompt = DECISION_PROMPT.format(
        store_name=merchant.store_name,
        mood=mood,
        brand_voice=brand_voice,
        brand_rules_summary=brand_rules_summary,
        products_summary=products_summary,
        anomaly_description=anomaly_desc,
    )

    try:
        raw = await _qwen_chat(
            model=get_settings().qwen_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.5,
            timeout=45.0,
        )
        data = _extract_json(raw)
    except BrandGenerationError as e:
        logger.error(f"[decision] Qwen failed for {merchant_id}: {e}")
        return None

    promo_id = f"ELEV_{merchant_id[:4].upper()}_{secrets.token_hex(3).upper()}"
    now = int(time.time() * 1000)

    # Coerce action_type to a valid enum value; default to flash_sale on unknown
    raw_type = str(data.get("action_type", "flash_sale")).strip()
    try:
        action_type_enum = AgentActionType(raw_type)
    except ValueError:
        logger.warning(f"[decision] unknown action_type '{raw_type}', defaulting to flash_sale")
        action_type_enum = AgentActionType.FLASH_SALE

    action_db = AgentActionDB(
        id=str(uuid4()),
        merchant_id=merchant_id,
        promo_id=promo_id,
        action_type=action_type_enum.value,
        trigger=str(data.get("trigger", anomaly_desc))[:500],
        title=str(data.get("title", "Action ready"))[:200],
        description=str(data.get("description", ""))[:500],
        estimated_gmv=float(data.get("estimated_gmv", 0) or 0),
        estimated_confidence=min(1.0, float(data.get("estimated_confidence", 0.7) or 0.7)),
        payload=data.get("payload") or {},
        brand_check=str(data.get("brand_check", ""))[:500],
        status="pending",
        created_at=now,
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

    # Push to merchant terminal via WebSocket
    from app.models.schemas import WSMessage
    await manager.push_to_terminal(
        merchant_id,
        WSMessage(
            event=WSEventType.AGENT_ACTION,
            payload={"action": action.model_dump()},
            merchant_id=merchant_id,
            timestamp=now,
        ),
    )

    logger.info(f"[decision] fired {action.action_type} action {action.id} for {merchant_id}")
    return action

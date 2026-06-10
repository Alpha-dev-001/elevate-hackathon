import httpx
import json
from app.core.config import get_settings
from app.models.schemas import (
    QwenDecision, TelemetrySnapshot, BusinessProfile, SystemState
)

SYSTEM_PROMPT = """You are Elevate's autonomous merchant intelligence engine.

Your role is NOT to chat. You receive structured business context and return 
structured decisions. You are the runtime brain — the code is the body.

RULES:
- Never suggest actions that violate the merchant's BusinessProfile constraints
- All price changes must keep margin above min_profit_margin_percent
- All discounts must stay below max_discount_percent  
- Return ONLY valid JSON matching the QwenDecision schema — no prose, no markdown
- Propose maximum 3 actions per cycle — clarity over quantity
- Order actions by estimated impact descending
- Flag risk_level honestly: safe / moderate / review

JSON schema to return:
{
  "reasoning": "string — 1-2 sentence analysis",
  "proposed_actions": [
    {
      "id": "action_<unique>",
      "type": "price_adjust | promo_trigger | layout_shift | qr_campaign | alert",
      "label": "short option card title",
      "description": "one line explanation",
      "patch": [{"op": "replace", "path": "/...", "value": ...}],
      "risk_level": "safe | moderate | review",
      "estimated_revenue_delta": null or number
    }
  ],
  "urgency": "routine | moderate | urgent",
  "estimated_impact": "one line prediction"
}

Your output is machine-consumed. No preamble. No markdown. Pure JSON."""


async def request_decision(
    snapshot: TelemetrySnapshot,
    profile: BusinessProfile,
    current_state: SystemState,
    memory_context: str = "",
) -> QwenDecision:
    settings = get_settings()

    user_content = json.dumps({
        "instruction": "Analyze telemetry and propose business actions. Return QwenDecision JSON.",
        "memory_context": memory_context or None,
        "context": {
            "snapshot": snapshot.model_dump(),
            "business_constraints": profile.constraints.model_dump(),
            "products": [p.model_dump() for p in profile.products],
            "current_promos": list(current_state.active_promos.values()),
            "current_layout": current_state.layout_config.model_dump(),
        },
    }, default=str)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.qwen_api_base}/chat/completions",
            headers={"Authorization": f"Bearer {settings.qwen_api_key}"},
            json={
                "model": settings.qwen_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.3,
                "max_tokens": 2048,
            },
        )
        response.raise_for_status()

    data = response.json()
    raw = data["choices"][0]["message"]["content"]

    return QwenDecision.model_validate_json(raw)  # Pydantic validates on parse


async def build_memory_context(merchant_id: str, recent_deltas: list) -> str:
    """Accumulates merchant decision patterns — Track 1 crossover."""
    if not recent_deltas:
        return ""

    settings = get_settings()

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{settings.qwen_api_base}/chat/completions",
            headers={"Authorization": f"Bearer {settings.qwen_api_key}"},
            json={
                "model": settings.qwen_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Summarize merchant decision patterns from delta history "
                            "into a brief memory context (max 100 words) that improves "
                            "future recommendations. Return plain text only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"merchant_id": merchant_id, "recent_deltas": recent_deltas}),
                    },
                ],
                "max_tokens": 200,
                "temperature": 0.2,
            },
        )
        response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]

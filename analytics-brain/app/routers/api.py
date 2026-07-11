import time
import base64
import io
import qrcode
from fastapi import APIRouter, HTTPException
from app.models.schemas import QRGenerateRequest, QRGenerateResponse, QRCampaign
from app.core.redis import get_redis, Keys
from app.core.config import get_settings

router = APIRouter(prefix="/api", tags=["api"])


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok", "service": "elevate-api"}


# ── QR Campaigns ───────────────────────────────────────────────────────────────

@router.post("/qr/generate", response_model=QRGenerateResponse)
async def generate_qr(req: QRGenerateRequest):
    settings = get_settings()
    campaign_id = f"qr_{req.merchant_id}_{req.product_id}_{int(time.time() * 1000)}"

    deep_link = (
        f"{settings.base_url}/scan"
        f"?c={campaign_id}&p={req.product_id}&m={req.merchant_id}"
        + (f"&promo={req.promo_id}" if req.promo_id else "")
    )

    campaign = QRCampaign(
        id=campaign_id,
        product_id=req.product_id,
        promo_id=req.promo_id,
        scan_count=0,
        created_at=int(time.time() * 1000),
        expires_at=(
            int(time.time() * 1000) + req.expires_in_hours * 3600 * 1000
            if req.expires_in_hours else None
        ),
        deep_link_url=deep_link,
    )

    redis = await get_redis()
    key = Keys.qr_campaign(req.merchant_id, campaign_id)
    ttl = req.expires_in_hours * 3600 if req.expires_in_hours else None

    if ttl:
        await redis.set(key, campaign.model_dump_json(), ex=ttl)
    else:
        await redis.set(key, campaign.model_dump_json())

    # Generate QR image as base64
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H)
    qr.add_data(deep_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_data_url = f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"

    return QRGenerateResponse(
        campaign=campaign,
        qr_data_url=qr_data_url,
        deep_link_url=deep_link,
    )


@router.get("/qr/scan")
async def record_scan(c: str, m: str):
    """Called when a QR code is scanned."""
    redis = await get_redis()
    key = Keys.qr_campaign(m, c)
    raw = await redis.get(key)

    if not raw:
        raise HTTPException(status_code=404, detail="Campaign not found or expired")

    campaign = QRCampaign.model_validate_json(raw)
    campaign.scan_count += 1
    await redis.set(key, campaign.model_dump_json())

    return {"campaign": campaign, "redirect": campaign.deep_link_url}


# ── Manual decision trigger (for demo / testing) ───────────────────────────────

@router.post("/decision/trigger/{merchant_id}")
async def trigger_decision(merchant_id: str):
    """
    Manually trigger a Qwen decision cycle.
    In production this fires automatically from telemetry anomalies.
    Useful for demos — trigger it and watch the terminal light up.
    """
    from app.services.decision_engine import run_decision_cycle
    from app.core.db import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        from app.core.redis import get_redis
        redis = await get_redis()
        action = await run_decision_cycle(
            merchant_id,
            "Manual trigger — demo/testing",
            db,
            redis,
        )

    if action is None:
        return {"triggered": False, "reason": "no action proposed or pending action exists"}

    return {
        "triggered": True,
        "action_id": action.id,
        "action_type": action.action_type.value,
        "title": action.title,
        "pushed_to_terminal": True,
    }

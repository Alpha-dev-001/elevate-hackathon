import time
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.models.schemas import (
    OnboardingSession, OnboardingStatus, GeneratedBrand,
    WSMessage, WSEventType, StoreCategory
)
from app.services.brand import analyze_logo, generate_brand
from app.services.interceptor import check_brand_tweak
from app.core.redis import get_redis, Keys
from app.core.ws_manager import manager
import json

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.post("/start")
async def start_onboarding(
    store_name: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    logo: UploadFile = File(...),
):
    """
    Step 1+2 combined: merchant submits store info + logo.
    Qwen-VL analyzes logo immediately.
    Returns logo analysis so frontend can show it while brand generation runs.
    """
    merchant_id = f"merchant_{uuid.uuid4().hex[:12]}"

    # Validate logo
    if logo.content_type not in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
        raise HTTPException(status_code=400, detail="Logo must be PNG, JPG, or WebP")

    logo_bytes = await logo.read()
    if len(logo_bytes) > 5 * 1024 * 1024:  # 5MB limit
        raise HTTPException(status_code=400, detail="Logo must be under 5MB")

    # Upload to OSS (simplified — returns URL)
    logo_url = await _upload_to_oss(merchant_id, logo_bytes, logo.content_type)

    # Qwen-VL analyzes the logo
    logo_analysis = await analyze_logo(logo_bytes, logo.content_type)

    # Initialize onboarding session
    session = OnboardingSession(
        merchant_id=merchant_id,
        store_name=store_name,
        category=StoreCategory(category),
        description=description,
        logo_url=logo_url,
        logo_analysis=logo_analysis,
        generated_brand=None,
        status=OnboardingStatus.LOGO_UPLOAD,
    )

    redis = await get_redis()
    await redis.set(
        Keys.onboarding(merchant_id),
        session.model_dump_json(),
    )

    return {
        "merchant_id": merchant_id,
        "logo_analysis": logo_analysis,
        "next_step": "generate-brand",
    }


@router.post("/generate-brand/{merchant_id}")
async def generate_store_brand(merchant_id: str):
    """
    Step 3: Qwen-Max generates full brand package + guard rules.
    This is the moment the store comes to life.
    """
    redis = await get_redis()
    raw = await redis.get(Keys.onboarding(merchant_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Onboarding session not found")

    session = OnboardingSession.model_validate_json(raw)
    if not session.logo_analysis:
        raise HTTPException(status_code=400, detail="Logo analysis required first")

    # Qwen generates full brand + guard rules
    brand = await generate_brand(
        logo_analysis=session.logo_analysis,
        store_name=session.store_name,
        category=session.category.value,
        description=session.description,
    )

    # Update session
    session.generated_brand = brand
    session.status = OnboardingStatus.BRAND_REVIEW
    await redis.set(Keys.onboarding(merchant_id), session.model_dump_json())

    # Cache brand separately for fast access during live operations
    await redis.set(Keys.brand(merchant_id), brand.model_dump_json())

    return {
        "brand": brand,
        "merchant_id": merchant_id,
        "next_step": "review and add products",
    }


@router.post("/check-tweak/{merchant_id}")
async def check_brand_tweak_route(merchant_id: str, tweak: dict):
    """
    Called in real time as merchant tweaks brand settings.
    Returns warnings from Qwen's own BrandGuardRules — the reflex layer.

    Frontend calls this on every color picker change, layout switch, etc.
    """
    redis = await get_redis()
    brand_raw = await redis.get(Keys.brand(merchant_id))
    if not brand_raw:
        raise HTTPException(status_code=404, detail="Brand not found")

    brand = GeneratedBrand.model_validate_json(brand_raw)
    warnings = check_brand_tweak(tweak, brand.brand_guard_rules)

    return {
        "warnings": [w.model_dump() for w in warnings],
        "safe": len(warnings) == 0,
    }


@router.post("/publish/{merchant_id}")
async def publish_store(merchant_id: str):
    """
    Step 4: Merchant is satisfied — store goes live.
    Initializes SystemState from brand data and activates telemetry.
    """
    from app.models.schemas import SystemState, LayoutConfig, BusinessConstraints, BusinessProfile
    from app.services.delta import save_state

    redis = await get_redis()
    session_raw = await redis.get(Keys.onboarding(merchant_id))
    brand_raw = await redis.get(Keys.brand(merchant_id))

    if not session_raw or not brand_raw:
        raise HTTPException(status_code=404, detail="Onboarding data not found")

    session = OnboardingSession.model_validate_json(session_raw)
    brand = GeneratedBrand.model_validate_json(brand_raw)

    # Build initial system state from brand
    initial_state = SystemState(
        version=1,
        last_updated=int(time.time() * 1000),
        products={},
        active_promos={},
        layout_config=LayoutConfig(
            banner_text=brand.hero_copy,
            color_accent=brand.color_palette.accent,
            layout_variant=brand.layout_variant,
        ),
        qr_campaigns={},
    )

    # Build business profile from brand guard rules
    business_profile = BusinessProfile(
        merchant_id=merchant_id,
        store_name=session.store_name,
        constraints=BusinessConstraints(
            min_profit_margin_percent=15.0,  # default — merchant adjusts later
            max_discount_percent=40.0,
            min_price={},
            brand_colors=[
                brand.color_palette.primary,
                brand.color_palette.accent,
                *brand.brand_guard_rules.protected_colors,
            ],
            accessibility_level="AA",
        ),
        products=[],
    )

    await save_state(merchant_id, initial_state)
    await redis.set(Keys.profile(merchant_id), business_profile.model_dump_json())

    # Update session status
    session.status = OnboardingStatus.LIVE
    await redis.set(Keys.onboarding(merchant_id), session.model_dump_json())

    return {
        "status": "live",
        "merchant_id": merchant_id,
        "store_name": session.store_name,
        "storefront_url": f"/storefront/{merchant_id}",
    }


async def _upload_to_oss(merchant_id: str, data: bytes, content_type: str) -> str:
    """
    Upload logo to Alibaba Cloud OSS.
    Returns the public URL.
    TODO: Wire up real OSS SDK when credentials are available.
    """
    from app.core.config import get_settings
    settings = get_settings()
    filename = f"logos/{merchant_id}/logo.png"
    # OSS upload implementation goes here
    # For now returns a placeholder that works for development
    return f"https://{settings.oss_bucket}.oss-{settings.oss_region}.aliyuncs.com/{filename}"

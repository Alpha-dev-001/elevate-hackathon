"""
Onboarding — the store comes alive.

The merchant signs up (auth), drops a logo (uploaded straight to OSS by the
frontend), and hands us the URL. From there:

  POST /onboarding/start    -> kicks off brand generation in the background,
                               returns immediately; the frontend waits on the
                               terminal WebSocket for `brand_ready`.
  GET  /onboarding/brand    -> the finished BrandPackage (recovery path if the
                               WS event was missed, and what the review page loads).
  POST /onboarding/publish  -> initialise SystemState + BusinessProfile, store
                               goes live at /s/{slug}.

FastAPI never touches file bytes — only the OSS URL string. The brand pipeline
fires qwen-vl-max -> qwen-max server-side and pushes the result over the socket.
Icons are upgraded a beat later in a second push so the reveal stays fast.
"""
from __future__ import annotations

import time
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, get_session_factory
from app.core.redis import get_redis, Keys
from app.core.security import get_current_merchant
from app.core.ws_manager import manager
from app.models.db_models import MerchantDB, BrandProfileDB
from app.models.schemas import (
    LogoSubmitRequest,
    BrandPackage,
    LogoAnalysis,
    GeneratedBrand,
    BrandGuardRules,
    SystemState,
    LayoutConfig,
    BusinessProfile,
    BusinessConstraints,
    OnboardingStatus,
    WSMessage,
    WSEventType,
)
from app.services import brand as brand_svc
from app.services.brand import BrandGenerationError
from app.services import delta as delta_svc
from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _now() -> int:
    return int(time.time() * 1000)


def _store_shell_url(slug: str) -> str:
    return f"{get_settings().frontend_url}/s/{slug}"


# ─── Persistence helpers (Postgres source of truth, Redis cache) ─────────────────

async def _save_brand_pg(db: AsyncSession, merchant_id: str, pkg: BrandPackage) -> None:
    """Upsert the brand into Postgres — what survives a Redis flush or restart."""
    row = await db.get(BrandProfileDB, merchant_id)
    generated = {"brand": pkg.brand.model_dump(), "guards": pkg.guards.model_dump()}
    if row is None:
        db.add(
            BrandProfileDB(
                merchant_id=merchant_id,
                logo_analysis=pkg.analysis.model_dump(),
                generated_brand=generated,
            )
        )
    else:
        row.logo_analysis = pkg.analysis.model_dump()
        row.generated_brand = generated
        row.updated_at = _now()


async def _cache_brand(merchant_id: str, pkg: BrandPackage) -> None:
    """Cache the package in Redis. Best-effort — Postgres is the real copy."""
    try:
        redis = await get_redis()
        await redis.set(Keys.brand(merchant_id), pkg.model_dump_json())
    except Exception as e:  # Redis down must never lose the brand
        logger.warning(f"[onboarding] Redis cache failed for {merchant_id}: {e}")


async def _set_phase(merchant_id: str, phase: str, error: str | None = None) -> None:
    """Fine-grained generation phase for the incubation page to recover from.

    phase ∈ {generating, ready, failed}. Stored in Redis only — coarse flow
    state lives on the merchant row. Best-effort; never raises.
    """
    import json
    try:
        redis = await get_redis()
        doc = {"phase": phase, "updated_at": _now()}
        if error:
            doc["error"] = error
        await redis.set(Keys.onboarding(merchant_id), json.dumps(doc))
    except Exception as e:
        logger.warning(f"[onboarding] could not set phase for {merchant_id}: {e}")


async def _load_brand(merchant_id: str, db: AsyncSession) -> BrandPackage | None:
    """Redis first (fast), Postgres fallback (durable)."""
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.brand(merchant_id))
        if raw:
            return BrandPackage.model_validate_json(raw)
    except Exception as e:
        logger.warning(f"[onboarding] Redis read failed for {merchant_id}: {e}")

    row = await db.get(BrandProfileDB, merchant_id)
    if row is None:
        return None
    try:
        return BrandPackage(
            analysis=LogoAnalysis(**row.logo_analysis),
            brand=GeneratedBrand(**row.generated_brand["brand"]),
            guards=BrandGuardRules(**row.generated_brand["guards"]),
        )
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"[onboarding] corrupt brand row for {merchant_id}: {e}")
        return None


async def _push_brand_ready(merchant_id: str, pkg: BrandPackage, slug: str) -> None:
    """Push the brand to the merchant's terminal socket. If they haven't
    connected yet, the GET /onboarding/brand recovery path covers it."""
    await manager.push_to_terminal(
        merchant_id,
        WSMessage(
            event=WSEventType.BRAND_READY,
            payload={
                "brand_package": pkg.model_dump(),
                "store_shell_url": _store_shell_url(slug),
            },
            merchant_id=merchant_id,
            timestamp=_now(),
        ),
    )


# ─── The background brand pipeline ───────────────────────────────────────────────

async def _run_brand_pipeline(
    merchant_id: str,
    slug: str,
    logo_url: str,
    store_name: str,
    category: str,
    description: str,
) -> None:
    """Fired after the /start response is sent. Two pushes: brand first (fast,
    deterministic icons), then real SVG icons morph in.

    Wrapped end to end — BackgroundTasks swallow exceptions, and a hung
    incubation screen is a P0 demo failure, so every path either pushes a
    result or pushes an error.
    """
    factory = get_session_factory()
    try:
        # Fast path: analysis -> brand + guards (icons are placeholder marks).
        pkg = await brand_svc.build_brand_package(
            logo_url, store_name, category, description
        )

        async with factory() as db:
            await _save_brand_pg(db, merchant_id, pkg)
            m = await db.get(MerchantDB, merchant_id)
            if m is not None:
                m.onboarding_status = OnboardingStatus.BRAND_REVIEW.value
            await db.commit()

        await _cache_brand(merchant_id, pkg)
        await _set_phase(merchant_id, "ready")
        await _push_brand_ready(merchant_id, pkg, slug)
        logger.info(f"[onboarding] brand_ready pushed for {merchant_id}")

        # Upgrade path: real SVG icons, off the critical reveal. If this fails
        # the deterministic marks already shipped — no harm, just log.
        try:
            icons = await brand_svc.generate_icons(
                store_name, pkg.brand.palette, pkg.analysis
            )
            pkg.brand.icons = icons
            async with factory() as db:
                await _save_brand_pg(db, merchant_id, pkg)
                await db.commit()
            await _cache_brand(merchant_id, pkg)
            await _push_brand_ready(merchant_id, pkg, slug)  # icons morph in
            logger.info(f"[onboarding] icons upgraded for {merchant_id}")
        except BrandGenerationError as e:
            logger.warning(f"[onboarding] icon upgrade failed for {merchant_id}: {e}")

        # BrandToken — off the critical path, never block reveal.
        try:
            from app.models.schemas import BrandToken
            brand_token_result = await brand_svc.generate_brand_token(pkg.analysis, store_name, category)

            async with factory() as db:
                # Store BrandToken if generation succeeded
                brand_profile = await db.get(BrandProfileDB, merchant_id)
                if brand_profile and isinstance(brand_token_result, BrandToken):
                    from app.services.layout_dsl import generate_layout_dsl
                    product_count = 0  # new store — merchant hasn't added products yet
                    brand_token_result.layout_dsl = await generate_layout_dsl(
                        brand_token_result, store_name, category, product_count,
                        slug=slug,
                    )
                    # Scoped micro-interaction CSS — best-effort, never blocks.
                    try:
                        from app.services.css_gen import generate_custom_css
                        brand_token_result.layout_dsl.custom_css = await generate_custom_css(
                            brand_token_result, slug,
                        )
                    except Exception as csse:
                        logger.warning("[onboarding] custom_css generation failed for %s: %s", merchant_id, csse)
                    brand_profile.brand_tokens = brand_token_result.model_dump()
                    # cache forever; invalidated on regenerate
                    try:
                        from app.core.redis import get_redis, Keys  # noqa: F401
                        r = await get_redis()
                        await r.set(
                            f"layout_dsl:{merchant_id}",
                            brand_token_result.layout_dsl.model_dump_json(),
                        )
                    except Exception as ce:
                        logger.warning("[onboarding] layout_dsl cache failed for %s: %s", merchant_id, ce)
                    logger.info(
                        f"[onboarding] BrandToken saved for {merchant_id}: "
                        f"layout.style={brand_token_result.layout.style} "
                        f"sections={len(brand_token_result.layout_dsl.sections)}"
                    )
                elif isinstance(brand_token_result, Exception):
                    logger.warning(
                        f"[onboarding] BrandToken generation failed for {merchant_id}: "
                        f"{brand_token_result}"
                    )

                await db.commit()
        except Exception as e:
            logger.warning(
                f"[onboarding] brand token step failed for {merchant_id}: {e}"
            )

    except BrandGenerationError as e:
        logger.error(f"[onboarding] brand pipeline failed for {merchant_id}: {e}")
        await _set_phase(merchant_id, "failed", str(e))
        await manager.push_to_terminal(
            merchant_id,
            WSMessage(
                event=WSEventType.BRAND_READY,
                payload={"error": str(e)},
                merchant_id=merchant_id,
                timestamp=_now(),
            ),
        )
    except Exception as e:  # truly unexpected — still must not hang the UI
        logger.exception(f"[onboarding] unexpected pipeline error for {merchant_id}")
        await _set_phase(merchant_id, "failed", "Brand generation failed unexpectedly")
        await manager.push_to_terminal(
            merchant_id,
            WSMessage(
                event=WSEventType.BRAND_READY,
                payload={"error": "Brand generation failed unexpectedly"},
                merchant_id=merchant_id,
                timestamp=_now(),
            ),
        )


# ─── Routes ──────────────────────────────────────────────────────────────────────

@router.post("/start", status_code=202)
async def start_onboarding(
    payload: LogoSubmitRequest,
    background: BackgroundTasks,
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Merchant submits their uploaded logo's OSS URL. We store it and kick off
    brand generation in the background; the frontend watches the terminal WS
    for `brand_ready`."""
    # Guard: a live store must never be re-onboarded — a fresh logo would
    # regenerate (and overwrite) its brand, logo, and layout. To brand a
    # different store, sign out and create a new account.
    if merchant.is_live:
        raise HTTPException(
            status_code=409,
            detail="Your store is already live. Sign out and create a new account to onboard a different brand.",
        )

    url = payload.logo_oss_url.strip()
    if not url or not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="logo_oss_url must be an http(s) URL")

    merchant.logo_url = url
    # get_db commits this on return, before the background task runs.

    await _set_phase(merchant.id, "generating")
    background.add_task(
        _run_brand_pipeline,
        merchant.id,
        merchant.slug,
        url,
        merchant.store_name,
        merchant.category,
        merchant.description or "",
    )
    return {"status": "generating", "merchant_id": merchant.id}


@router.get("/brand")
async def get_brand(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """The finished BrandPackage. Recovery path for a missed WS event and the
    source the brand-review page loads from."""
    pkg = await _load_brand(merchant.id, db)
    if pkg is not None:
        return {
            "brand_package": pkg.model_dump(),
            "store_shell_url": _store_shell_url(merchant.slug),
        }

    # Not ready — tell the client whether it's still cooking or it failed.
    import json
    phase, error = "not_started", None
    try:
        redis = await get_redis()
        raw = await redis.get(Keys.onboarding(merchant.id))
        if raw:
            doc = json.loads(raw)
            phase, error = doc.get("phase", "not_started"), doc.get("error")
    except Exception:
        pass
    raise HTTPException(status_code=409, detail={"status": phase, "error": error})


@router.post("/publish")
async def publish_store(
    merchant: MerchantDB = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Store goes live. Initialises SystemState (hot-reload source) and the
    BusinessProfile (interceptor constraints) from the brand, flips the merchant
    live, and returns the public URL."""
    # Re-publishing a live store would reset its SystemState (wiping active promos
    # and layout). Publishing is a one-time onboarding step — block it once live.
    if merchant.is_live:
        raise HTTPException(
            status_code=409,
            detail="Your store is already live. Use the store builder to make changes.",
        )

    pkg = await _load_brand(merchant.id, db)
    if pkg is None:
        raise HTTPException(status_code=409, detail="Generate your brand before publishing")

    # Seed with whatever products were added during onboarding (may be none —
    # a zero-product store publishes fine into the "preparing the shelves" state).
    from app.services.products import products_state_map

    initial_state = SystemState(
        version=1,
        last_updated=_now(),
        products=await products_state_map(db, merchant.id),
        active_promos={},
        layout_config=LayoutConfig(
            banner_text=pkg.brand.tagline,
            color_accent=pkg.brand.palette.accent,
            layout_variant=pkg.brand.layout_variant,
        ),
        qr_campaigns={},
    )
    profile = BusinessProfile(
        merchant_id=merchant.id,
        store_name=merchant.store_name,
        constraints=BusinessConstraints(),  # sane defaults — merchant tunes later
        products=[],
    )

    # SystemState lives in Redis — the storefront hot-reloads from it. If the
    # state layer is unreachable the store genuinely cannot go live, so fail
    # cleanly (503) rather than leaking a raw 500.
    try:
        await delta_svc.save_state(merchant.id, initial_state)
        redis = await get_redis()
        await redis.set(Keys.profile(merchant.id), profile.model_dump_json())
    except Exception as e:
        logger.error(f"[onboarding] publish failed — state layer down for {merchant.id}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Store can't go live right now — the state service is unavailable. Try again.",
        )

    merchant.is_live = True
    merchant.onboarding_status = OnboardingStatus.LIVE.value

    # Broadcast so any open storefront morphs to the freshly-published layout/state
    # live — the merchant-drives-the-store half of the pipeline. Best-effort; the
    # publish already succeeded, a WS blip must not fail it.
    try:
        import json
        await manager.push_to_all(
            merchant.id,
            WSMessage(
                event=WSEventType.STATE_UPDATED,
                payload={"state": json.loads(initial_state.model_dump_json())},
                merchant_id=merchant.id,
                timestamp=_now(),
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[onboarding] publish broadcast failed for {merchant.id}: {e}")

    return {
        "status": "live",
        "store_name": merchant.store_name,
        "storefront_url": f"/s/{merchant.slug}",
    }

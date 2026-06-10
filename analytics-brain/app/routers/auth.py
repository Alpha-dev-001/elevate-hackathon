"""
Merchant auth — signup, login, logout, me.
JWT in httpOnly cookie. bcrypt hashes. Merchant row in Postgres.
Onboarding state lives on the Merchant (onboarding_status) — no session model.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    SESSION_COOKIE,
    create_access_token,
    get_current_merchant,
    hash_password,
    verify_password,
)
from app.models.db_models import MerchantDB
from app.models.schemas import (
    Merchant,
    MerchantCreate,
    MerchantLogin,
    OnboardingStatus,
    generate_slug,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_schema(m: MerchantDB) -> Merchant:
    return Merchant(
        id=m.id,
        email=m.email,
        store_name=m.store_name,
        slug=m.slug,
        logo_url=m.logo_url or "",
        category=m.category,
        onboarding_status=m.onboarding_status,
        is_live=m.is_live,
    )


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=settings.jwt_expires_minutes * 60,
        path="/",
    )


@router.post("/signup", response_model=Merchant, status_code=201)
async def signup(
    payload: MerchantCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(MerchantDB.id).where(MerchantDB.email == payload.email)
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        )

    slug = generate_slug(payload.store_name)
    slug_taken = await db.scalar(select(MerchantDB.id).where(MerchantDB.slug == slug))
    if slug_taken:
        slug = generate_slug(payload.store_name, suffix=True)

    merchant = MerchantDB(
        id=f"merchant_{uuid.uuid4().hex[:12]}",
        email=payload.email,
        hashed_password=hash_password(payload.password),
        store_name=payload.store_name,
        slug=slug,
        category=payload.category.value,
        description=payload.description,
        # store info arrives with signup — next step is the logo drop
        onboarding_status=OnboardingStatus.LOGO_UPLOAD.value,
    )
    db.add(merchant)
    await db.flush()

    _set_session_cookie(response, create_access_token(merchant.id))
    return _to_schema(merchant)


@router.post("/login", response_model=Merchant)
async def login(
    payload: MerchantLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    merchant = await db.scalar(
        select(MerchantDB).where(MerchantDB.email == payload.email)
    )
    if not merchant or not verify_password(payload.password, merchant.hashed_password):
        # same message for unknown email and wrong password — no enumeration
        raise HTTPException(status_code=401, detail="Invalid email or password")

    _set_session_cookie(response, create_access_token(merchant.id))
    return _to_schema(merchant)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=Merchant)
async def me(merchant: MerchantDB = Depends(get_current_merchant)):
    return _to_schema(merchant)

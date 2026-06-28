"""Per-brand customer auth — register / login / logout / me, all scoped to one
store by slug. A customer of `haree` is a different account from a customer of
`crest` (same email allowed at both). JWT role=customer in a separate httpOnly
cookie from the merchant session.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import (
    CUSTOMER_COOKIE,
    create_customer_token,
    get_current_customer,
    hash_password,
    verify_password,
)
from app.models.db_models import MerchantDB, CustomerDB
from app.models.schemas import Customer, CustomerCreate, CustomerLogin

router = APIRouter(prefix="/s/{slug}/auth", tags=["customer-auth"])


def _to_schema(c: CustomerDB, slug: str) -> Customer:
    return Customer(id=c.id, merchant_id=c.merchant_id, store_slug=slug, email=c.email, name=c.name)


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=CUSTOMER_COOKIE, value=token, httponly=True, samesite="lax",
        secure=settings.app_env == "production",
        max_age=settings.jwt_expires_minutes * 60, path="/",
    )


async def _store_or_404(slug: str, db: AsyncSession) -> MerchantDB:
    m = await db.scalar(select(MerchantDB).where(MerchantDB.slug == slug))
    if m is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return m


@router.post("/register", response_model=Customer, status_code=201)
async def register(slug: str, payload: CustomerCreate, response: Response, db: AsyncSession = Depends(get_db)):
    store = await _store_or_404(slug, db)
    existing = await db.scalar(
        select(CustomerDB.id)
        .where(CustomerDB.merchant_id == store.id)
        .where(CustomerDB.email == payload.email)
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already have an account at this store — sign in instead")

    customer = CustomerDB(
        id=f"cust_{uuid.uuid4().hex[:12]}",
        merchant_id=store.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        name=payload.name,
    )
    db.add(customer)
    await db.flush()
    _set_cookie(response, create_customer_token(customer.id, store.id))
    return _to_schema(customer, slug)


@router.post("/login", response_model=Customer)
async def login(slug: str, payload: CustomerLogin, response: Response, db: AsyncSession = Depends(get_db)):
    store = await _store_or_404(slug, db)
    customer = await db.scalar(
        select(CustomerDB)
        .where(CustomerDB.merchant_id == store.id)
        .where(CustomerDB.email == payload.email)
    )
    if not customer or not verify_password(payload.password, customer.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    _set_cookie(response, create_customer_token(customer.id, store.id))
    return _to_schema(customer, slug)


@router.post("/logout")
async def logout(slug: str, response: Response):
    response.delete_cookie(key=CUSTOMER_COOKIE, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=Customer)
async def me(slug: str, customer: CustomerDB = Depends(get_current_customer)):
    return _to_schema(customer, slug)

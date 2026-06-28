"""
Auth primitives — bcrypt password hashing + JWT session tokens.
The token travels in an httpOnly cookie, never localStorage.
No OAuth, no magic links, no 2FA — demo scope.
"""
import time
import bcrypt
import jwt
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.models.db_models import MerchantDB, CustomerDB

SESSION_COOKIE = "elevate_session"       # merchant role
CUSTOMER_COOKIE = "elevate_customer"     # customer role (per-brand)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        # malformed hash in DB — treat as auth failure, not a 500
        return False


def create_access_token(merchant_id: str, role: str = "merchant") -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": merchant_id,
        "role": role,
        "iat": now,
        "exp": now + settings.jwt_expires_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_customer_token(customer_id: str, merchant_id: str) -> str:
    """Customer session token — carries role=customer and the store it belongs to."""
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": customer_id,
        "role": "customer",
        "store": merchant_id,
        "iat": now,
        "exp": now + settings.jwt_expires_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_payload(token: str) -> dict:
    """Decode + verify a token into its payload. Raises 401 on any failure."""
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")


def decode_token(token: str) -> str:
    """Returns merchant_id. Rejects customer tokens (role separation). Tokens
    minted before RBAC carry no role and are still accepted as merchant."""
    payload = decode_payload(token)
    if payload.get("role") == "customer":
        raise HTTPException(status_code=403, detail="Customer token cannot access merchant resources")
    merchant_id = payload.get("sub")
    if not merchant_id:
        raise HTTPException(status_code=401, detail="Invalid session token")
    return merchant_id


async def get_current_merchant(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> MerchantDB:
    """FastAPI dependency — resolves the session cookie to a live merchant row."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    merchant_id = decode_token(session_token)
    merchant = await db.get(MerchantDB, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=401, detail="Merchant no longer exists")
    return merchant


async def get_current_customer(
    slug: str,
    customer_token: str | None = Cookie(default=None, alias=CUSTOMER_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> CustomerDB:
    """FastAPI dependency for customer-only routes. Verifies the token is a
    customer token AND that the customer belongs to THIS store (slug)."""
    if not customer_token:
        raise HTTPException(status_code=401, detail="Not signed in")
    payload = decode_payload(customer_token)
    if payload.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Not a customer session")
    customer = await db.get(CustomerDB, payload.get("sub"))
    if customer is None:
        raise HTTPException(status_code=401, detail="Customer no longer exists")
    merchant = await db.get(MerchantDB, customer.merchant_id)
    if merchant is None or merchant.slug != slug:
        raise HTTPException(status_code=403, detail="This account belongs to a different store")
    return customer

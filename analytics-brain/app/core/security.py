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
from app.models.db_models import MerchantDB

SESSION_COOKIE = "elevate_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        # malformed hash in DB — treat as auth failure, not a 500
        return False


def create_access_token(merchant_id: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": merchant_id,
        "iat": now,
        "exp": now + settings.jwt_expires_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> str:
    """Returns merchant_id. Raises 401 on expiry, tampering, or bad shape."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
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

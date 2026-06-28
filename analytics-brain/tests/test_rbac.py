"""RBAC token role separation — pure, no DB/server."""
import pytest
from fastapi import HTTPException
from app.core.security import (
    create_access_token, create_customer_token, decode_token, decode_payload,
)


def test_merchant_token_carries_role_and_decodes():
    tok = create_access_token("merchant_abc")
    assert decode_payload(tok)["role"] == "merchant"
    assert decode_token(tok) == "merchant_abc"


def test_customer_token_rejected_by_merchant_decode():
    tok = create_customer_token("cust_xyz", "merchant_abc")
    p = decode_payload(tok)
    assert p["role"] == "customer"
    assert p["store"] == "merchant_abc"
    with pytest.raises(HTTPException) as ei:
        decode_token(tok)            # customer token must not pass as merchant
    assert ei.value.status_code == 403


def test_legacy_merchant_token_without_role_still_accepted():
    # tokens minted before RBAC carried no "role" — must still resolve.
    import jwt, time
    from app.core.config import get_settings
    s = get_settings()
    legacy = jwt.encode(
        {"sub": "merchant_old", "iat": int(time.time()), "exp": int(time.time()) + 3600},
        s.jwt_secret, algorithm=s.jwt_algorithm,
    )
    assert decode_token(legacy) == "merchant_old"

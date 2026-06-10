"""
Auth flow integration test — full HTTP layer against a SQLite-backed DB.

Run:  .venv/Scripts/python.exe tests/test_auth.py
The get_db dependency is overridden so no Postgres is required; the same
flows run against real Postgres simply by starting docker compose and
hitting the live server.
"""
import asyncio
import atexit
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db

# File-backed SQLite + NullPool: every connection is fresh, so nothing stays
# bound to a dead event loop (asyncio.run here vs TestClient's anyio loop).
_db_path = os.path.join(tempfile.gettempdir(), "elevate_test_auth.db")
if os.path.exists(_db_path):
    os.remove(_db_path)
atexit.register(lambda: os.path.exists(_db_path) and os.remove(_db_path))

engine = create_async_engine(f"sqlite+aiosqlite:///{_db_path}", poolclass=NullPool)
factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def _override_db():
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def main() -> int:
    asyncio.run(_create_tables())
    app.dependency_overrides[get_db] = _override_db
    client = TestClient(app)

    signup_payload = {
        "email": "emma@example.com",
        "store_name": "Emma Fashion",
        "password": "a-strong-password",
        "category": "fashion",
        "description": "Minimal womenswear",
    }

    # 1. signup -> 201, session cookie, clean slug, status advanced to logo_upload
    r = client.post("/auth/signup", json=signup_payload)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "emma-fashion", body
    assert body["onboarding_status"] == "logo_upload", body
    assert body["logo_url"] == "" and body["is_live"] is False, body
    assert "hashed_password" not in body, "password material leaked in response!"
    assert "elevate_session" in r.cookies, "session cookie not set on signup"
    print("1. signup: 201, clean slug, httpOnly session cookie, no hash leak")

    # 2. /auth/me with the cookie -> same merchant
    r = client.get("/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "emma@example.com"
    print("2. /auth/me resolves the cookie to the merchant")

    # 3. duplicate email -> 409
    r = client.post("/auth/signup", json=signup_payload)
    assert r.status_code == 409, r.text
    print("3. duplicate email rejected with 409")

    # 4. same store name, new email -> slug gets collision suffix
    r = client.post("/auth/signup", json={**signup_payload, "email": "emma2@example.com"})
    assert r.status_code == 201, r.text
    slug2 = r.json()["slug"]
    assert slug2.startswith("emma-fashion-") and slug2 != "emma-fashion", slug2
    print(f"4. slug collision suffixed: {slug2}")

    # 5. login: wrong password and unknown email -> identical 401s (no enumeration)
    r_wrong = client.post("/auth/login", json={"email": "emma@example.com", "password": "nope-nope-nope"})
    r_unknown = client.post("/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"})
    assert r_wrong.status_code == r_unknown.status_code == 401
    assert r_wrong.json() == r_unknown.json(), "login errors are distinguishable"
    print("5. wrong password / unknown email indistinguishable 401s")

    # 6. login with correct credentials -> 200 + fresh cookie
    r = client.post("/auth/login", json={"email": "emma@example.com", "password": "a-strong-password"})
    assert r.status_code == 200, r.text
    print("6. login ok")

    # 7. logout clears the session -> /auth/me -> 401
    r = client.post("/auth/logout")
    assert r.status_code == 200
    r = client.get("/auth/me")
    assert r.status_code == 401, f"session survived logout: {r.status_code}"
    print("7. logout kills the session")

    # 8. no cookie at all -> 401
    r = TestClient(app).get("/auth/me")
    assert r.status_code == 401
    print("8. /auth/me without cookie -> 401")

    # 9. validation: short password / bad email -> 422 before touching the DB
    r = client.post("/auth/signup", json={**signup_payload, "email": "x@y.dev", "password": "short"})
    assert r.status_code == 422
    r = client.post("/auth/signup", json={**signup_payload, "email": "not-an-email"})
    assert r.status_code == 422
    print("9. weak password and malformed email rejected with 422")

    # 10. tampered cookie -> 401
    bad = TestClient(app)
    bad.cookies.set("elevate_session", "evil.token.value")
    r = bad.get("/auth/me")
    assert r.status_code == 401
    print("10. tampered session cookie -> 401")

    print("ALL AUTH INTEGRATION CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

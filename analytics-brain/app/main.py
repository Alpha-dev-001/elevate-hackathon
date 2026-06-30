from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import get_settings
from app.core.database import get_engine, Base
from app.models import db_models  # noqa: F401 — registers tables on Base.metadata
from app.routers import ws, upload, auth, onboarding, products, store, shop, merchant, dev, behavior, agent, dashboard, brand, customer_auth
import logging

# Stale scaffold router still excluded until rewritten against current schemas.py:
#   app.routers.api — imports removed QRGenerateRequest/Response; rewrite at the
#                     QR/health step of the build order

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Elevate API",
    description="Autonomous merchant intelligence engine — the brain behind the store.",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ws.router)          # WebSocket connections
app.include_router(upload.router)      # STS tokens for direct OSS upload
app.include_router(auth.router)        # merchant signup / login / session
app.include_router(customer_auth.router)  # sprint-4: per-brand customer register/login
app.include_router(onboarding.router)  # logo -> brand -> publish
app.include_router(products.router)    # single add + CSV batch + list + CRUD
app.include_router(store.router)       # public storefront data by slug
app.include_router(shop.router)        # public cart + checkout + order lookup
app.include_router(merchant.router)    # orders, promos, constraints, catalog review
app.include_router(behavior.router)    # behavior event ingest + simulation
app.include_router(agent.router)       # pending actions, approve, dismiss
app.include_router(dashboard.router)   # attribution dashboard
app.include_router(brand.router)       # sprint-3: layout DSL save/regenerate + StoreBirth SSE

if settings.app_env == "development":
    app.include_router(dev.router)     # dev-only: brand regeneration for existing stores


# ── DB bootstrap ────────────────────────────────────────────────────────────
# Columns not yet captured in a migration file (Sprint 2 orders cols +
# brand_tokens). create_all creates missing TABLES only, never missing COLUMNS,
# so these need an explicit, idempotent ALTER. Applied on every startup.
_INLINE_PATCHES = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS subtotal DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name VARCHAR DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_email VARCHAR DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at BIGINT DEFAULT 0",
    "ALTER TABLE brand_profiles ADD COLUMN IF NOT EXISTS brand_tokens JSONB",
]

# migrations/*.sql live one level up from app/ (copied into the image via COPY . .)
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _split_sql(sql: str) -> list[str]:
    """Strip `--` comment lines, then split into individual statements.

    asyncpg rejects multiple statements in one execute(), so each statement must
    be sent separately. Comment lines are dropped first so a leading comment
    doesn't get glued onto (and swallow) the statement that follows it.
    """
    body = "\n".join(
        ln for ln in sql.splitlines() if not ln.strip().startswith("--")
    )
    return [s.strip() for s in body.split(";") if s.strip()]


async def _bootstrap_database() -> None:
    """Create missing tables and apply idempotent migrations, in EVERY env.

    create_all is purely additive (creates missing tables, never drops/alters),
    and every migration here is `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`, so
    this is safe on a fresh RDS and on an already-seeded dev DB alike. This is
    what makes a from-zero production deploy work with no manual SQL step.
    TODO: replace with Alembic for real migration history (see UPGRADES.md §6).
    """
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)          # 1. base schema
        for stmt in _INLINE_PATCHES:                            # 2. uncaptured cols
            await conn.execute(text(stmt))
        for sql_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):  # 3. .sql migrations
            for stmt in _split_sql(sql_file.read_text(encoding="utf-8")):
                await conn.execute(text(stmt))


@app.on_event("startup")
async def startup():
    logger.info("Elevate API starting up")
    logger.info(f"Frontend: {settings.frontend_url}")
    logger.info(f"Qwen model: {settings.qwen_model}")

    try:
        await _bootstrap_database()
        logger.info("Database schema bootstrapped (tables + migrations applied)")
    except Exception as e:
        logger.error(
            f"DB bootstrap failed — auth and persistence will fail: {e}"
        )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "service": "Elevate API",
        "status": "alive",
        "websockets": {
            "terminal": "ws://host/ws/terminal/{merchant_id}",
            "storefront": "ws://host/ws/storefront/{merchant_id}",
        },
    }

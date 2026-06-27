from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import get_engine, Base
from app.models import db_models  # noqa: F401 — registers tables on Base.metadata
from app.routers import ws, upload, auth, onboarding, products, store, shop, merchant, dev, behavior, agent, dashboard
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
app.include_router(onboarding.router)  # logo -> brand -> publish
app.include_router(products.router)    # single add + CSV batch + list + CRUD
app.include_router(store.router)       # public storefront data by slug
app.include_router(shop.router)        # public cart + checkout + order lookup
app.include_router(merchant.router)    # orders, promos, constraints, catalog review
app.include_router(behavior.router)    # behavior event ingest + simulation
app.include_router(agent.router)       # pending actions, approve, dismiss
app.include_router(dashboard.router)   # attribution dashboard

if settings.app_env == "development":
    app.include_router(dev.router)     # dev-only: brand regeneration for existing stores


@app.on_event("startup")
async def startup():
    logger.info("Elevate API starting up")
    logger.info(f"Frontend: {settings.frontend_url}")
    logger.info(f"Qwen model: {settings.qwen_model}")

    if settings.app_env == "development":
        # Dev convenience: sync tables to models. Production uses Alembic
        # migrations against RDS — create_all never runs there.
        from sqlalchemy import text

        # create_all only creates missing TABLES, not missing COLUMNS. The
        # Sprint 2 additions to the existing `orders` table need an explicit,
        # idempotent ALTER so an already-seeded dev DB picks them up.
        _SCHEMA_PATCHES = [
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS subtotal DOUBLE PRECISION DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name VARCHAR DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_email VARCHAR DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at BIGINT DEFAULT 0",
            "ALTER TABLE brand_profiles ADD COLUMN IF NOT EXISTS brand_tokens JSONB",
        ]
        try:
            async with get_engine().begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                for stmt in _SCHEMA_PATCHES:
                    await conn.execute(text(stmt))
            logger.info("Database tables synced")
        except Exception as e:
            logger.error(
                f"Database unreachable — auth and persistence will fail: {e}"
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

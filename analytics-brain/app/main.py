from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import get_engine, Base
from app.models import db_models  # noqa: F401 — registers tables on Base.metadata
from app.routers import ws, upload, auth, onboarding, products, store
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
app.include_router(products.router)    # single add + CSV batch + list
app.include_router(store.router)       # public storefront data by slug


@app.on_event("startup")
async def startup():
    logger.info("Elevate API starting up")
    logger.info(f"Frontend: {settings.frontend_url}")
    logger.info(f"Qwen model: {settings.qwen_model}")

    if settings.app_env == "development":
        # Dev convenience: sync tables to models. Production uses Alembic
        # migrations against RDS — create_all never runs there.
        try:
            async with get_engine().begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.routers import ws, api, onboarding, upload
import logging

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
app.include_router(ws.router)            # WebSocket connections
app.include_router(upload.router)        # STS tokens for direct OSS upload
app.include_router(onboarding.router)    # Onboarding + brand generation
app.include_router(api.router)           # QR, health, decision trigger


@app.on_event("startup")
async def startup():
    logger.info("Elevate API starting up")
    logger.info(f"Frontend: {settings.frontend_url}")
    logger.info(f"Qwen model: {settings.qwen_model}")


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

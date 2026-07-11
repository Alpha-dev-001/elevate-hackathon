import redis.asyncio as aioredis
from functools import lru_cache
from app.core.config import get_settings

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
        )
    return _client


# ─── Key schema ───────────────────────────────────────────────────────────────

class Keys:
    @staticmethod
    def system_state(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:state"

    @staticmethod
    def snapshot(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:snapshot:latest"

    @staticmethod
    def delta_log(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:deltas"

    @staticmethod
    def product_velocity(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:velocity"

    @staticmethod
    def active_sessions(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:active_sessions"

    @staticmethod
    def session_events(session_id: str) -> str:
        return f"elevate:session:{session_id}"

    @staticmethod
    def pending_actions(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:pending_actions"

    @staticmethod
    def qr_campaign(merchant_id: str, campaign_id: str) -> str:
        return f"elevate:{merchant_id}:qr:{campaign_id}"

    @staticmethod
    def brand(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:brand"

    @staticmethod
    def profile(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:profile"

    @staticmethod
    def onboarding(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:onboarding"

    @staticmethod
    def cart(merchant_id: str, session_id: str) -> str:
        return f"elevate:{merchant_id}:cart:{session_id}"

    @staticmethod
    def catalog_review(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:catalog_review"

    @staticmethod
    def events(merchant_id: str) -> str:
        return f"elevate:{merchant_id}:events"

    @staticmethod
    def qwen_usage(merchant_id: str) -> str:
        """Per-call Qwen usage log — capped list, newest first."""
        return f"elevate:{merchant_id}:qwen_usage"


# ─── TTLs (seconds) ───────────────────────────────────────────────────────────

class TTL:
    SNAPSHOT = 300          # 5 min
    SESSION = 1800          # 30 min
    PENDING_ACTIONS = 3600  # 1 hour
    DELTA_LOG = 86400 * 7   # 7 days
    CART = 86400 * 2        # 2 days — outlives a browse session but stays ephemeral
    CATALOG_REVIEW = 86400  # 1 day — cached Qwen observation, re-run on demand
    EVENTS = 3600           # 1 hour — behavior events; only need last N for decision cycle
    QWEN_USAGE = 86400 * 7  # 7 days — token usage log per merchant

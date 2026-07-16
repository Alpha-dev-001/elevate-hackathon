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
    def next_price_check(product_id: str) -> str:
        """When this product is next due for a PRICE_REBALANCE reasoning
        pass — set by pricing_cycle.record_pricing_check_result."""
        return f"elevate:price_check:{product_id}:next"

    @staticmethod
    def price_check_escalation(product_id: str) -> str:
        """Consecutive-hourly-check streak while a product is in escalated
        cadence — decays back to daily after PRICE_REVIEW_ESCALATION_DECAY_TICKS
        quiet ticks. Absent key == not currently escalated."""
        return f"elevate:price_check:{product_id}:escalation_streak"

    @staticmethod
    def reverting_products() -> str:
        """Global set of product_ids currently stepping back toward baseline
        after a comparable-informed move showed engagement without
        conversion. Membership is added by pricing_cycle.check_reversion_triggers,
        removed by pricing_cycle.apply_reversions once baseline is reached or
        a purchase occurs."""
        return "elevate:reverting_products"

    @staticmethod
    def active_carts(merchant_id: str) -> str:
        """Set of session_ids with a currently non-empty cart for this
        merchant — the enumeration index cart_dwell.py's periodic tick needs
        (carts are otherwise only addressable by a known (merchant_id,
        session_id) pair, with no way to list "all carts for a merchant")."""
        return f"elevate:{merchant_id}:active_carts"

    @staticmethod
    def dwell_offer(merchant_id: str, session_id: str) -> str:
        """A cart_dwell_nudge discount scoped to exactly this session — never
        read by any other session's checkout. Self-expiring (set_dwell_offer
        sets the Redis TTL to match the offer's own expires_at), so a merchant
        approving a new dwell nudge for a stale session can never leave a
        zombie discount behind."""
        return f"elevate:{merchant_id}:dwell:{session_id}"

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

    @staticmethod
    def duplicate_dismissed(merchant_id: str, group_hash: str) -> str:
        """Suppression marker — a dismissed duplicate-merge proposal for this
        exact group of product_ids is blocked from re-firing until this key
        expires (DUPLICATE_DISMISS_TTL_SECONDS, default 7 days)."""
        return f"elevate:{merchant_id}:dup_dismissed:{group_hash}"


# ─── TTLs (seconds) ───────────────────────────────────────────────────────────

class TTL:
    SNAPSHOT = 300          # 5 min
    SESSION = 1800          # 30 min
    PENDING_ACTIONS = 3600  # 1 hour
    DELTA_LOG = 86400 * 7   # 7 days
    CART = 86400 * 2        # 2 days — outlives a browse session but stays ephemeral
    CATALOG_REVIEW = 86400  # 1 day — cached Qwen observation, re-run on demand
    # 25h (not 24h) — the daily signal-rollup job (pricing_signals.rollup_daily_signals)
    # reads "yesterday's" events once a day; a plain 24h TTL risks the list expiring
    # in the gap between "last event of the day" and "the job actually runs". Real-
    # time anomaly detection (behavior_tracker) only ever reads the first 100 of the
    # capped 500-item list regardless of TTL, so this is a zero-cost change for it.
    EVENTS = 90000          # 25 hours — long enough for the once-daily signal rollup
    QWEN_USAGE = 86400 * 7  # 7 days — token usage log per merchant

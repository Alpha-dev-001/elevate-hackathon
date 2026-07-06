from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Qwen Cloud ────────────────────────────────────────
    qwen_api_key: str
    # International Model Studio keys (sk-ws-...) MUST use the -intl endpoint;
    # the mainland host 401s them. Override in .env if using a China-region key.
    qwen_api_base: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-max"
    qwen_vl_model: str = "qwen-vl-max"

    # ── Alibaba Cloud Redis (Tair) ────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # ── Alibaba Cloud OSS ─────────────────────────────────
    oss_region: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket: str = "elevate-assets"

    # ── Database (Alibaba Cloud RDS PostgreSQL) ───────────
    database_url: str = "postgresql+asyncpg://elevate:elevate_dev@localhost:5432/elevate"

    # ── Auth ──────────────────────────────────────────────
    jwt_secret: str  # required — startup fails if missing from .env
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 7  # 7 days — hackathon-friendly session

    # ── Autopilot action defaults ─────────────────────────
    # Deterministic FALLBACKS only — Qwen chooses the real discount/duration in
    # its decision payload; these apply when it omits one. The upper bound on any
    # discount is never set here: it's the merchant's max_discount_percent
    # business constraint (interceptor Layer 2). Same env-configurable pattern as
    # ANOMALY_THRESHOLD.
    recovery_default_discount_percent: float = 10.0
    flash_sale_default_discount_percent: float = 15.0
    scarcity_default_discount_percent: float = 10.0
    agent_action_duration_minutes: int = 30
    # Grounded revenue-impact estimate = anomaly_count × avg catalog price × rate.
    # These replace Qwen's ungrounded guess so the number is real + explainable.
    recovery_gmv_rate: float = 0.5   # expected recovered $ per abandoned cart
    flash_gmv_rate: float = 0.15     # expected uplift $ per surged view

    # ── App ───────────────────────────────────────────────
    app_env: str = "development"
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Tolerate unknown env vars (e.g. deploy-only ACR_NAMESPACE, or FC
        # platform vars) instead of crashing the whole backend on startup.
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()

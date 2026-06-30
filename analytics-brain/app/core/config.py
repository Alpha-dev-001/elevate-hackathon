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

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Qwen Cloud ────────────────────────────────────────
    qwen_api_key: str
    qwen_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-max"

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

    # ── App ───────────────────────────────────────────────
    app_env: str = "development"
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()

    # ── Database (Alibaba Cloud RDS PostgreSQL) ────────────────────────────
    database_url: str = "postgresql+asyncpg://localhost/elevate"

"""
core/config.py
──────────────
Centralised settings loaded from environment variables.
In AWS the environment variables are injected from:
  • ECS Task Definition → SSM Parameter Store
  • Secrets Manager  (DB password, JWT secret)
All values have safe defaults for local dev.
"""

from __future__ import annotations
import json
import os
from functools import lru_cache
from typing import Optional

from pydantic import field_validator, AnyHttpUrl, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────
    APP_NAME: str = "NoteFlow"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"       # development | staging | production
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── API ────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    SECRET_KEY: str = "change-me-in-production-use-secrets-manager"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24        # 1 day
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ── Database (RDS PostgreSQL) ──────────────────
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "noteflow"
    DATABASE_USER: str = "noteflow"
    DATABASE_PASSWORD: str = "dev_password"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_ECHO: bool = False            # set True to log SQL

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    # ── Redis (ElastiCache) ───────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_SSL: bool = False                # True in prod (ElastiCache TLS)

    @property
    def redis_url(self) -> str:
        scheme = "rediss" if self.REDIS_SSL else "redis"
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"{scheme}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ── AWS ───────────────────────────────────────
    AWS_REGION: str = "us-east-1"
    AWS_ACCOUNT_ID: str = ""

    # S3 (file attachments & exports)
    S3_BUCKET_ATTACHMENTS: str = "noteflow-attachments"
    S3_BUCKET_EXPORTS: str = "noteflow-exports"
    S3_PRESIGNED_URL_EXPIRY: int = 3600   # seconds

    # SES (email notifications)
    SES_FROM_EMAIL: str = "noreply@noteflow.app"
    SES_ENABLED: bool = False

    # SNS (push / mobile notifications)
    SNS_TOPIC_ARN: str = ""

    # CloudWatch
    CLOUDWATCH_LOG_GROUP: str = "/noteflow/api"
    CLOUDWATCH_METRICS_NAMESPACE: str = "NoteFlow/API"

    # Secrets Manager (optional — overrides DB/JWT if set)
    SECRETS_MANAGER_ARN: str = ""

    # ── Celery ────────────────────────────────────
    CELERY_BROKER_URL: str = ""           # defaults to redis_url at runtime
    CELERY_RESULT_BACKEND: str = ""

    # ── Sentry ───────────────────────────────────
    SENTRY_DSN: str = ""

    # ── Rate limiting ─────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 120

    # ── Pagination ────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.
    In AWS, if SECRETS_MANAGER_ARN is set, pull sensitive values
    from Secrets Manager and merge them in at startup.
    """
    settings = Settings()

    # Pull from AWS Secrets Manager if configured
    if settings.SECRETS_MANAGER_ARN:
        try:
            import boto3
            client = boto3.client("secretsmanager", region_name=settings.AWS_REGION)
            response = client.get_secret_value(SecretId=settings.SECRETS_MANAGER_ARN)
            secret = json.loads(response["SecretString"])
            # Override sensitive fields
            for key, val in secret.items():
                if hasattr(settings, key.upper()):
                    object.__setattr__(settings, key.upper(), val)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Could not load from Secrets Manager: {e}"
            )

    return settings

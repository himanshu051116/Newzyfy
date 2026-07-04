from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.local", ".env"),
        env_prefix="NEWSINTEL_",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://newsintel:newsintel@localhost:5432/newsintel"
    database_connect_timeout_seconds: float = Field(default=5.0, ge=1, le=60)
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    object_store_endpoint: str = "http://localhost:9000"
    object_store_bucket: str = "newsintel"
    object_store_access_key: str = "newsintel"
    object_store_secret_key: SecretStr = SecretStr("change-me")
    crawler_user_agent: str = (
        "NewsIntelligenceBot/0.1 (+https://example.invalid/crawler)"
    )
    ai_provider: Literal["disabled", "local"] = "disabled"
    local_model_base_url: str = "http://localhost:11434"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    public_base_url: str = "http://127.0.0.1:8000"
    auth_mode: Literal["disabled", "oidc", "jwt"] = "disabled"
    auth_provider_name: str = "oidc"
    auth_jwt_issuer: str | None = None
    auth_jwt_audience: str | None = None
    auth_jwt_jwks_url: str | None = None
    auth_jwt_algorithms: str = "RS256"
    auth_jwt_hs256_secret: SecretStr = SecretStr("")
    auth_oidc_authorization_url: str | None = None
    auth_oidc_token_url: str | None = None
    auth_oidc_client_id: str | None = None
    auth_oidc_client_secret: SecretStr = SecretStr("")
    auth_oidc_redirect_uri: str | None = None
    auth_session_secret: SecretStr = SecretStr("")
    auth_session_ttl_seconds: int = Field(default=3_600, ge=300, le=86_400)
    auth_cookie_name: str = "newsintel_session"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    auth_csrf_cookie_name: str = "newsintel_csrf"
    dev_auth_bypass_enabled: bool = False
    dev_auth_provider: str = "dev-local"
    dev_auth_user_id: str = "local-owner"
    dev_auth_email: str = "owner.local@example.invalid"
    dev_auth_display_name: str = "Local Owner"
    bootstrap_owner_provider: str | None = None
    bootstrap_owner_user_id: str | None = None
    bootstrap_owner_email: str | None = None
    cors_allowed_origins: str = ""
    fetch_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    fetch_max_bytes: int = Field(default=8_000_000, ge=1024, le=50_000_000)
    poll_worker_batch_size: int = Field(default=20, ge=1, le=500)
    poll_worker_concurrency: int = Field(default=5, ge=1, le=100)
    poll_worker_lease_seconds: int = Field(default=120, ge=30, le=3_600)
    poll_worker_idle_seconds: float = Field(default=2.0, ge=0.1, le=60)
    outbox_worker_batch_size: int = Field(default=50, ge=1, le=1_000)
    outbox_worker_idle_seconds: float = Field(default=2.0, ge=0.1, le=60)
    database_retry_max_seconds: float = Field(default=30.0, ge=1, le=300)
    article_worker_batch_size: int = Field(default=20, ge=1, le=500)
    article_worker_concurrency: int = Field(default=5, ge=1, le=100)
    article_worker_lease_seconds: int = Field(default=120, ge=30, le=3_600)
    article_worker_idle_seconds: float = Field(default=2.0, ge=0.1, le=60)
    article_fetch_max_attempts: int = Field(default=3, ge=1, le=20)
    article_fetch_retry_base_seconds: int = Field(default=120, ge=1, le=86_400)
    article_fetch_retry_max_seconds: int = Field(default=3_600, ge=1, le=604_800)
    article_fetch_retry_jitter_ratio: float = Field(default=0.15, ge=0, le=1)
    recent_article_window_hours: int = Field(default=48, ge=1, le=168)
    max_new_urls_per_channel_poll: int = Field(default=200, ge=1, le=1_000)
    max_new_urls_per_publisher_fetch: int = Field(default=300, ge=1, le=10_000)
    max_new_urls_per_fetch_job: int = Field(default=2_000, ge=1, le=100_000)
    max_active_channels_per_publisher: int = Field(default=25, ge=1, le=500)
    discovery_recovery_window_days: int = Field(default=7, ge=1, le=90)
    initial_backfill_days: int = Field(default=3, ge=0, le=365)
    max_retries: int = Field(default=3, ge=1, le=20)
    worker_lease_seconds: int = Field(default=120, ge=30, le=3_600)
    dead_letter_after_attempts: int = Field(default=3, ge=1, le=50)
    raw_artifact_dir: str = "artifacts/raw-html"
    raw_artifact_store_backend: Literal["local", "s3"] = "local"
    s3_artifact_prefix: str = "raw-html"
    s3_artifact_sse: str | None = None

    @model_validator(mode="after")
    def reject_unsafe_production_defaults(self) -> "Settings":
        if self.environment == "production":
            unsafe = {
                "object_store_secret_key": (
                    self.object_store_secret_key.get_secret_value() == "change-me"
                ),
                "crawler_user_agent": "example.invalid" in self.crawler_user_agent,
                "auth_mode": self.auth_mode == "disabled",
                "auth_session_secret": len(self.auth_session_secret.get_secret_value()) < 32,
                "dev_auth_bypass_enabled": self.dev_auth_bypass_enabled,
                "auth_cookie_secure": not self.auth_cookie_secure,
                "cors_allowed_origins": "*" in self.cors_origin_list,
                "raw_artifact_store_backend": self.raw_artifact_store_backend != "s3",
                "auth_jwt_issuer": not self.auth_jwt_issuer,
                "auth_jwt_audience": not self.auth_jwt_audience,
            }
            if self.auth_mode in {"oidc", "jwt"}:
                unsafe["auth_jwt_jwks_url"] = (
                    "HS256" not in self.auth_algorithm_list
                    and not self.auth_jwt_jwks_url
                )
            if self.auth_mode == "oidc":
                unsafe.update(
                    {
                        "auth_oidc_authorization_url": not self.auth_oidc_authorization_url,
                        "auth_oidc_token_url": not self.auth_oidc_token_url,
                        "auth_oidc_client_id": not self.auth_oidc_client_id,
                        "auth_oidc_client_secret": (
                            len(self.auth_oidc_client_secret.get_secret_value()) < 16
                        ),
                    }
                )
            bad = [name for name, enabled in unsafe.items() if enabled]
            if bad:
                raise ValueError(f"unsafe production defaults: {', '.join(bad)}")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.cors_allowed_origins.split(",")
            if item.strip()
        ]

    @property
    def auth_algorithm_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.auth_jwt_algorithms.split(",")
            if item.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

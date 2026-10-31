"""Application settings, loaded from environment variables (never from source code)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CMMS_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    # Runtime connection uses the least-privilege application role.
    database_url: str = "postgresql+psycopg://cmms_app:dev_app_pw@localhost:5432/cmms"
    # Migrations use the schema-owner role.
    migration_database_url: str | None = None

    session_ttl_hours: int = 12
    session_idle_minutes: int = 120
    cookie_secure: bool = True
    cookie_domain: str | None = None
    cors_origins: list[str] = Field(default_factory=list)

    login_max_attempts: int = 5
    login_window_minutes: int = 15
    login_lockout_minutes: int = 15
    rate_limit_per_minute: int = 300
    login_rate_limit_per_minute: int = 20

    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./var/storage"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    signed_url_seconds: int = 300
    max_upload_mb: int = 25

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True

    scheduler_enabled: bool = True
    # Shown as a red banner on every page, e.g. "TEST copy": marks a test installation so nobody mistakes it for the real one.
    instance_label: str = ""
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)


@lru_cache
def get_settings() -> Settings:
    return Settings()

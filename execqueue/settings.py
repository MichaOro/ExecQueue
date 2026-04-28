"""Central runtime configuration for ExecQueue."""

from enum import Enum
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeEnvironment(str, Enum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class OpenCodeOperatingMode(str, Enum):
    """Supported OpenCode runtime modes."""

    DISABLED = "disabled"
    EXTERNAL_ENDPOINT = "external_endpoint"


def validate_database_driver(database_url: str | None, field_name: str) -> str | None:
    """Require explicit SQLAlchemy driver names for PostgreSQL URLs."""
    if database_url is None:
        return None

    scheme = urlsplit(database_url).scheme
    if scheme == "postgresql":
        raise ValueError(
            f"{field_name} must use 'postgresql+psycopg://' instead of 'postgresql://'."
        )
    return database_url


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_env: RuntimeEnvironment = Field(
        default=RuntimeEnvironment.DEVELOPMENT,
        description="Explicit runtime environment used for safe configuration selection.",
    )
    database_url: str | None = Field(
        default=None,
        description="Primary PostgreSQL connection URL for non-test runtime contexts.",
    )
    database_url_test: str | None = Field(
        default=None,
        description="Dedicated PostgreSQL connection URL for tests only.",
    )
    database_echo: bool = Field(
        default=False,
        description="Enable SQLAlchemy statement logging for local debugging.",
    )
    database_pool_pre_ping: bool = Field(
        default=True,
        description="Validate pooled connections before use to avoid stale PostgreSQL connections.",
    )
    database_pool_size: int = Field(
        default=5,
        ge=1,
        description="Base SQLAlchemy connection pool size.",
    )
    database_max_overflow: int = Field(
        default=10,
        ge=0,
        description="Extra temporary connections allowed above the base pool size.",
    )
    database_pool_timeout: int = Field(
        default=30,
        ge=1,
        description="Seconds to wait for a pooled database connection.",
    )

    telegram_bot_token: str | None = Field(
        default=None,
        description="Telegram Bot API token. Required only if bot is enabled.",
    )
    telegram_bot_enabled: bool = Field(
        default=False,
        description="Whether the Telegram bot is enabled.",
    )
    telegram_polling_timeout: int = Field(
        default=30,
        ge=1,
        le=60,
        description="Timeout for Telegram polling in seconds (1-60).",
    )
    telegram_shutdown_timeout: int = Field(
        default=8,
        ge=1,
        le=60,
        description="Maximum graceful shutdown time for the Telegram bot in seconds.",
    )
    telegram_admin_user_id: str | None = Field(
        default=None,
        description="User ID for admin notifications (optional). Use your Telegram user ID.",
    )
    system_admin_token: str | None = Field(
        default=None,
        description="Shared secret required for privileged system restart API endpoints.",
    )
    telegram_notification_user_id: str | None = Field(
        default=None,
        description="User ID for notification events (DEPRECATED: Use DB subscriptions instead).",
    )
    execqueue_api_host: str = Field(
        default="127.0.0.1",
        description="Host used by the local API orchestrator.",
    )
    execqueue_api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port used by the local API orchestrator.",
    )
    execqueue_api_app: str = Field(
        default="execqueue.main:app",
        description="ASGI application import path used by the local API orchestrator.",
    )

    opencode_mode: OpenCodeOperatingMode = Field(
        default=OpenCodeOperatingMode.DISABLED,
        description="OpenCode integration mode: disabled or external_endpoint.",
    )
    opencode_base_url: str = Field(
        default="http://127.0.0.1:4096",
        description="Base URL of the externally managed OpenCode HTTP service.",
    )
    opencode_timeout_ms: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="Timeout for OpenCode reachability checks in milliseconds.",
    )

    @field_validator("database_url", "database_url_test")
    @classmethod
    def validate_postgres_driver(cls, value: str | None, info) -> str | None:
        """Reject implicit PostgreSQL driver selection to keep runtime and Alembic aligned."""
        return validate_database_driver(value, info.field_name.upper())

    @field_validator("opencode_base_url")
    @classmethod
    def validate_opencode_base_url(cls, value: str) -> str:
        """Require an explicit HTTP(S) base URL for OpenCode."""
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OPENCODE_BASE_URL must be a valid http(s) URL.")
        return value.rstrip("/") or value

    @property
    def is_test_environment(self) -> bool:
        """Return whether the runtime must use isolated test infrastructure."""
        return self.app_env is RuntimeEnvironment.TEST

    @property
    def active_database_url(self) -> str:
        """Return the database URL for the active runtime without implicit fallback."""
        if self.is_test_environment:
            if not self.database_url_test:
                raise ValueError(
                    "DATABASE_URL_TEST must be set when APP_ENV=test or pytest is running."
                )
            return self.database_url_test

        if not self.database_url:
            raise ValueError(
                "DATABASE_URL must be set for development and production runtimes."
            )
        return self.database_url

    @property
    def opencode_enabled(self) -> bool:
        """Return whether OpenCode endpoint reachability should be evaluated."""
        return self.opencode_mode is OpenCodeOperatingMode.EXTERNAL_ENDPOINT

    def model_post_init(self, __context: object) -> None:
        """Validate environment-specific database settings with no prod/test fallback."""
        if self.is_test_environment and self.database_url and self.database_url_test:
            if self.database_url == self.database_url_test:
                raise ValueError(
                    "DATABASE_URL and DATABASE_URL_TEST must not point to the same database."
                )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

"""Central runtime configuration for ExecQueue."""

from enum import Enum
from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeEnvironment(str, Enum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


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

    # Telegram Bot Configuration
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
    telegram_admin_user_id: str | None = Field(
        default=None,
        description="User ID for admin notifications (optional). Use your Telegram user ID.",
    )
    telegram_notification_user_id: str | None = Field(
        default=None,
        description="User ID for notification events like bot online (optional). Use your Telegram user ID.",
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

    @model_validator(mode="after")
    def validate_runtime_database_configuration(self) -> "Settings":
        """Validate environment-specific database settings with no prod/test fallback."""
        if self.is_test_environment and self.database_url and self.database_url_test:
            if self.database_url == self.database_url_test:
                raise ValueError(
                    "DATABASE_URL and DATABASE_URL_TEST must not point to the same database."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

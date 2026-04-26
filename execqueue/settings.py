"""Central runtime configuration for ExecQueue."""

from functools import lru_cache
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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
    telegram_admin_chat_id: str | None = Field(
        default=None,
        description="Chat ID for admin notifications (optional).",
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

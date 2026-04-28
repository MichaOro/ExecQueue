"""Tests for application settings and configuration."""

import os
from unittest.mock import patch

import pytest
from pydantic_settings import SettingsConfigDict

from execqueue.settings import OpenCodeOperatingMode, RuntimeEnvironment, Settings, get_settings


class TestSettingsDefaults:
    def test_runtime_defaults(self):
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()

        assert settings.app_env is RuntimeEnvironment.DEVELOPMENT
        assert settings.telegram_bot_enabled is False
        assert settings.execqueue_api_host == "127.0.0.1"
        assert settings.execqueue_api_port == 8000
        assert settings.opencode_mode is OpenCodeOperatingMode.DISABLED
        assert settings.opencode_base_url == "http://127.0.0.1:4096"
        assert settings.opencode_timeout_ms == 1000


class TestSettingsFromEnvironment:
    def test_loads_opencode_settings_from_environment(self):
        with patch.dict(
            os.environ,
            {
                "OPENCODE_MODE": "enabled",
                "OPENCODE_BASE_URL": "http://127.0.0.1:5000",
                "OPENCODE_TIMEOUT_MS": "1500",
            },
            clear=False,
        ):
            settings = Settings()

        assert settings.opencode_mode is OpenCodeOperatingMode.ENABLED
        assert settings.opencode_base_url == "http://127.0.0.1:5000"
        assert settings.opencode_timeout_ms == 1500

    def test_legacy_acp_variables_are_ignored(self):
        with patch.dict(
            os.environ,
            {
                "ACP_ENABLED": "true",
                "ACP_AUTO_START": "true",
                "ACP_START_COMMAND": "python -m acp",
            },
            clear=False,
        ):
            settings = Settings()

        assert settings.opencode_mode is OpenCodeOperatingMode.DISABLED

    def test_get_settings_uses_database_url_test_when_app_env_is_test(self):
        get_settings.cache_clear()
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "DATABASE_URL": "postgresql+psycopg://user:secret@localhost:5432/execqueue",
                "DATABASE_URL_TEST": (
                    "postgresql+psycopg://user:secret@localhost:5432/execqueue_test"
                ),
            },
            clear=False,
        ):
            settings = get_settings()

        assert settings.app_env is RuntimeEnvironment.TEST
        assert (
            settings.active_database_url
            == "postgresql+psycopg://user:secret@localhost:5432/execqueue_test"
        )


class TestSettingsValidation:
    def test_database_url_requires_explicit_psycopg_driver(self):
        with pytest.raises(ValueError, match="postgresql\\+psycopg://"):
            Settings(database_url="postgresql://user:secret@localhost:5432/execqueue")

    def test_active_database_url_requires_primary_database(self):
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings(app_env=RuntimeEnvironment.PRODUCTION)

        with pytest.raises(ValueError, match="DATABASE_URL must be set"):
            _ = settings.active_database_url

    def test_active_database_url_requires_test_database(self):
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings(
            app_env=RuntimeEnvironment.TEST,
            database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
        )

        with pytest.raises(ValueError, match="DATABASE_URL_TEST must be set"):
            _ = settings.active_database_url

    def test_database_urls_must_not_match_across_prod_and_test(self):
        with pytest.raises(ValueError, match="must not point to the same database"):
            Settings(
                app_env=RuntimeEnvironment.TEST,
                database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
                database_url_test="postgresql+psycopg://user:secret@localhost:5432/execqueue",
            )

    def test_opencode_mode_rejects_local_managed_process(self):
        with pytest.raises(ValueError):
            Settings(opencode_mode="local_managed_process")

    def test_opencode_base_url_requires_http_scheme(self):
        with pytest.raises(ValueError, match="valid http"):
            Settings(opencode_base_url="tcp://127.0.0.1:4096")

    def test_opencode_enabled_property(self):
        disabled = Settings(opencode_mode=OpenCodeOperatingMode.DISABLED)
        enabled = Settings(opencode_mode=OpenCodeOperatingMode.ENABLED)

        assert disabled.opencode_enabled is False
        assert enabled.opencode_enabled is True


class TestGetSettings:
    def test_get_settings_returns_settings_instance(self):
        assert isinstance(get_settings(), Settings)

    def test_get_settings_caches_result(self):
        assert get_settings() is get_settings()

    def test_reset_cache_for_new_settings(self):
        get_settings.cache_clear()
        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "true"}):
            settings1 = get_settings()

        get_settings.cache_clear()

        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "false"}):
            settings2 = get_settings()

        assert settings1.telegram_bot_enabled is True
        assert settings2.telegram_bot_enabled is False

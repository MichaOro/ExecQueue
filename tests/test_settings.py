"""Tests for application settings and configuration."""

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic_settings import SettingsConfigDict

from execqueue.settings import RuntimeEnvironment, Settings, get_settings


class TestSettingsDefaults:
    """Tests for default settings values."""

    def test_app_env_default(self):
        """Test that app_env defaults to development."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()
        assert settings.app_env is RuntimeEnvironment.DEVELOPMENT

    def test_database_url_default(self):
        """Test that database_url defaults to None."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()
        assert settings.database_url is None

    def test_database_url_test_default(self):
        """Test that database_url_test defaults to None."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()
        assert settings.database_url_test is None

    def test_telegram_bot_token_default(self):
        """Test that telegram_bot_token defaults to None."""
        # Create a new Settings class without env_file
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.telegram_bot_token is None

    def test_telegram_bot_enabled_default(self):
        """Test that telegram_bot_enabled defaults to False."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.telegram_bot_enabled is False

    def test_telegram_polling_timeout_default(self):
        """Test that telegram_polling_timeout defaults to 30."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.telegram_polling_timeout == 30

    def test_telegram_admin_user_id_default(self):
        """Test that telegram_admin_user_id defaults to None."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.telegram_admin_user_id is None

    def test_execqueue_api_host_default(self):
        """Test that execqueue_api_host defaults to 127.0.0.1."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.execqueue_api_host == "127.0.0.1"

    def test_execqueue_api_port_default(self):
        """Test that execqueue_api_port defaults to 8000."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.execqueue_api_port == 8000

    def test_acp_enabled_default(self):
        """Test that acp_enabled defaults to False."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.acp_enabled is False

    def test_acp_host_default(self):
        """Test that acp_host defaults to 127.0.0.1."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()
        assert settings.acp_host == "127.0.0.1"

    def test_acp_port_default(self):
        """Test that acp_port defaults to 8010."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()
        assert settings.acp_port == 8010

    def test_acp_auto_start_default(self):
        """Test that acp_auto_start defaults to False."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()
        assert settings.acp_auto_start is False

    def test_acp_start_command_default(self):
        """Test that acp_start_command defaults to None."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings()
        assert settings.acp_start_command is None

    def test_acp_endpoint_url_default(self):
        """Test that acp_endpoint_url defaults to None."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.acp_endpoint_url is None

    def test_acp_api_key_default(self):
        """Test that acp_api_key defaults to None."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.acp_api_key is None

    def test_acp_timeout_default(self):
        """Test that acp_timeout defaults to 30."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.acp_timeout == 30

    def test_acp_retry_count_default(self):
        """Test that acp_retry_count defaults to 3."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.acp_retry_count == 3


class TestSettingsFromEnvironment:
    """Tests for settings loaded from environment variables."""

    def test_app_env_from_env(self):
        """Test that app_env is loaded from environment."""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            settings = Settings()
            assert settings.app_env is RuntimeEnvironment.PRODUCTION

    def test_database_url_from_env(self):
        """Test that database_url is loaded from environment."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql+psycopg://user:secret@localhost:5432/execqueue"},
            clear=False,
        ):
            settings = Settings()
            assert (
                settings.database_url
                == "postgresql+psycopg://user:secret@localhost:5432/execqueue"
            )

    def test_database_url_test_from_env(self):
        """Test that database_url_test is loaded from environment."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL_TEST": (
                    "postgresql+psycopg://user:secret@localhost:5432/execqueue_test"
                )
            },
            clear=False,
        ):
            settings = Settings()
            assert (
                settings.database_url_test
                == "postgresql+psycopg://user:secret@localhost:5432/execqueue_test"
            )

    def test_get_settings_uses_database_url_test_when_app_env_is_test(self):
        """Test that cached settings select the explicit test DB in test runtime."""
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

    def test_database_url_requires_explicit_psycopg_driver(self):
        """Test that PostgreSQL URLs must declare the psycopg driver explicitly."""
        with pytest.raises(ValueError, match="postgresql\\+psycopg://"):
            Settings(database_url="postgresql://user:secret@localhost:5432/execqueue")

    def test_telegram_bot_token_from_env(self):
        """Test that telegram_bot_token is loaded from environment."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test_token_123"}):
            settings = Settings()
            assert settings.telegram_bot_token == "test_token_123"

    def test_telegram_bot_enabled_from_env_true(self):
        """Test that telegram_bot_enabled is loaded from environment."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "true"}):
            settings = Settings()
            assert settings.telegram_bot_enabled is True

    def test_telegram_bot_enabled_from_env_false(self):
        """Test that telegram_bot_enabled can be set to false."""
        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "false"}):
            settings = Settings()
            assert settings.telegram_bot_enabled is False

    def test_telegram_polling_timeout_from_env(self):
        """Test that telegram_polling_timeout is loaded from environment."""
        with patch.dict(os.environ, {"TELEGRAM_POLLING_TIMEOUT": "45"}):
            settings = Settings()
            assert settings.telegram_polling_timeout == 45

    def test_telegram_admin_user_id_from_env(self):
        """Test that telegram_admin_user_id is loaded from environment."""
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_USER_ID": "123456789"}):
            from execqueue.settings import get_settings
            get_settings.cache_clear()
            
            settings = get_settings()
            assert settings.telegram_admin_user_id == "123456789"

    def test_execqueue_api_host_from_env(self):
        """Test that execqueue_api_host is loaded from environment."""
        with patch.dict(os.environ, {"EXECQUEUE_API_HOST": "0.0.0.0"}):
            settings = Settings()
            assert settings.execqueue_api_host == "0.0.0.0"

    def test_execqueue_api_port_from_env(self):
        """Test that execqueue_api_port is loaded from environment."""
        with patch.dict(os.environ, {"EXECQUEUE_API_PORT": "9000"}):
            settings = Settings()
            assert settings.execqueue_api_port == 9000

    def test_acp_enabled_from_env_true(self):
        """Test that acp_enabled is loaded from environment."""
        with patch.dict(os.environ, {"ACP_ENABLED": "true"}):
            settings = Settings()
            assert settings.acp_enabled is True

    def test_acp_enabled_from_env_false(self):
        """Test that acp_enabled can be set to false."""
        with patch.dict(os.environ, {"ACP_ENABLED": "false"}):
            settings = Settings()
            assert settings.acp_enabled is False

    def test_acp_host_from_env(self):
        """Test that acp_host is loaded from environment."""
        with patch.dict(os.environ, {"ACP_HOST": "0.0.0.0"}):
            settings = Settings()
            assert settings.acp_host == "0.0.0.0"

    def test_acp_port_from_env(self):
        """Test that acp_port is loaded from environment."""
        with patch.dict(os.environ, {"ACP_PORT": "9010"}):
            settings = Settings()
            assert settings.acp_port == 9010

    def test_acp_auto_start_from_env(self):
        """Test that acp_auto_start is loaded from environment."""
        with patch.dict(os.environ, {"ACP_AUTO_START": "true"}):
            settings = Settings()
            assert settings.acp_auto_start is True

    def test_acp_start_command_from_env(self):
        """Test that acp_start_command is loaded from environment."""
        with patch.dict(os.environ, {"ACP_START_COMMAND": "python -m opencode_acp"}):
            settings = Settings()
            assert settings.acp_start_command == "python -m opencode_acp"

    def test_acp_endpoint_url_from_env(self):
        """Test that acp_endpoint_url is loaded from environment."""
        with patch.dict(
            os.environ,
            {"ACP_ENDPOINT_URL": "https://api.acp.example.com/v1"},
        ):
            settings = Settings()
            assert settings.acp_endpoint_url == "https://api.acp.example.com/v1"

    def test_acp_api_key_from_env(self):
        """Test that acp_api_key is loaded from environment."""
        with patch.dict(os.environ, {"ACP_API_KEY": "test-api-key-123"}):
            settings = Settings()
            assert settings.acp_api_key == "test-api-key-123"

    def test_acp_timeout_from_env(self):
        """Test that acp_timeout is loaded from environment."""
        with patch.dict(os.environ, {"ACP_TIMEOUT": "60"}):
            settings = Settings()
            assert settings.acp_timeout == 60

    def test_acp_retry_count_from_env(self):
        """Test that acp_retry_count is loaded from environment."""
        with patch.dict(os.environ, {"ACP_RETRY_COUNT": "5"}):
            settings = Settings()
            assert settings.acp_retry_count == 5


class TestSettingsValidation:
    """Tests for settings validation."""

    def test_active_database_url_uses_primary_database_outside_tests(self):
        """Test that non-test runtime uses DATABASE_URL."""
        settings = Settings(
            app_env=RuntimeEnvironment.DEVELOPMENT,
            database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
        )
        assert (
            settings.active_database_url
            == "postgresql+psycopg://user:secret@localhost:5432/execqueue"
        )

    def test_active_database_url_uses_test_database_in_test_env(self):
        """Test that test runtime uses DATABASE_URL_TEST."""
        settings = Settings(
            app_env=RuntimeEnvironment.TEST,
            database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
            database_url_test="postgresql+psycopg://user:secret@localhost:5432/execqueue_test",
        )
        assert (
            settings.active_database_url
            == "postgresql+psycopg://user:secret@localhost:5432/execqueue_test"
        )

    def test_active_database_url_requires_primary_database(self):
        """Test that non-test runtime does not silently continue without DATABASE_URL."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings(app_env=RuntimeEnvironment.PRODUCTION)

        with pytest.raises(ValueError, match="DATABASE_URL must be set"):
            _ = settings.active_database_url

    def test_active_database_url_requires_test_database(self):
        """Test that test runtime does not fall back to the primary database."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")

        settings = TestSettings(
            app_env=RuntimeEnvironment.TEST,
            database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
        )

        with pytest.raises(ValueError, match="DATABASE_URL_TEST must be set"):
            _ = settings.active_database_url

    def test_database_urls_must_not_match_across_prod_and_test(self):
        """Test that test and primary database URLs cannot be identical."""
        with pytest.raises(ValueError, match="must not point to the same database"):
            Settings(
                app_env=RuntimeEnvironment.TEST,
                database_url="postgresql+psycopg://user:secret@localhost:5432/execqueue",
                database_url_test="postgresql+psycopg://user:secret@localhost:5432/execqueue",
            )

    def test_telegram_polling_timeout_minimum(self):
        """Test that polling timeout respects minimum value."""
        with patch.dict(os.environ, {"TELEGRAM_POLLING_TIMEOUT": "1"}):
            settings = Settings()
            assert settings.telegram_polling_timeout == 1

    def test_telegram_polling_timeout_maximum(self):
        """Test that polling timeout respects maximum value."""
        with patch.dict(os.environ, {"TELEGRAM_POLLING_TIMEOUT": "60"}):
            settings = Settings()
            assert settings.telegram_polling_timeout == 60

    def test_api_port_minimum(self):
        """Test that API port respects minimum value."""
        with patch.dict(os.environ, {"EXECQUEUE_API_PORT": "1"}):
            settings = Settings()
            assert settings.execqueue_api_port == 1

    def test_api_port_maximum(self):
        """Test that API port respects maximum value."""
        with patch.dict(os.environ, {"EXECQUEUE_API_PORT": "65535"}):
            settings = Settings()
            assert settings.execqueue_api_port == 65535

    def test_acp_timeout_minimum(self):
        """Test that acp_timeout respects minimum value."""
        with patch.dict(os.environ, {"ACP_TIMEOUT": "1"}):
            settings = Settings()
            assert settings.acp_timeout == 1

    def test_acp_port_minimum(self):
        """Test that acp_port respects minimum value."""
        with patch.dict(os.environ, {"ACP_PORT": "1"}):
            settings = Settings()
            assert settings.acp_port == 1

    def test_acp_port_maximum(self):
        """Test that acp_port respects maximum value."""
        with patch.dict(os.environ, {"ACP_PORT": "65535"}):
            settings = Settings()
            assert settings.acp_port == 65535

    def test_acp_timeout_maximum(self):
        """Test that acp_timeout respects maximum value."""
        with patch.dict(os.environ, {"ACP_TIMEOUT": "120"}):
            settings = Settings()
            assert settings.acp_timeout == 120

    def test_acp_retry_count_minimum(self):
        """Test that acp_retry_count respects minimum value."""
        with patch.dict(os.environ, {"ACP_RETRY_COUNT": "0"}):
            settings = Settings()
            assert settings.acp_retry_count == 0

    def test_acp_retry_count_maximum(self):
        """Test that acp_retry_count respects maximum value."""
        with patch.dict(os.environ, {"ACP_RETRY_COUNT": "10"}):
            settings = Settings()
            assert settings.acp_retry_count == 10


class TestGetSettings:
    """Tests for the get_settings function."""

    def test_get_settings_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_caches_result(self):
        """Test that get_settings caches the result."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_ignores_subsequent_env_changes(self):
        """Test that cached settings ignore environment changes."""
        # First call caches the settings
        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "true"}):
            settings1 = get_settings()

        # Change environment
        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "false"}):
            settings2 = get_settings()

        # Cached settings should still have original value
        assert settings1.telegram_bot_enabled is True
        assert settings2.telegram_bot_enabled is True

    def test_reset_cache_for_new_settings(self):
        """Test that we can reset the cache for new settings."""
        # Clear cache
        get_settings.cache_clear()

        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "true"}):
            settings1 = get_settings()

        get_settings.cache_clear()

        with patch.dict(os.environ, {"TELEGRAM_BOT_ENABLED": "false"}):
            settings2 = get_settings()

        assert settings1.telegram_bot_enabled is True
        assert settings2.telegram_bot_enabled is False

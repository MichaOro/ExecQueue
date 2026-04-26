"""Tests for application settings and configuration."""

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic_settings import SettingsConfigDict

from execqueue.settings import Settings, get_settings


class TestSettingsDefaults:
    """Tests for default settings values."""

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

    def test_telegram_admin_chat_id_default(self):
        """Test that telegram_admin_chat_id defaults to None."""
        class TestSettings(Settings):
            model_config = SettingsConfigDict(env_file="", extra="ignore")
        
        settings = TestSettings()
        assert settings.telegram_admin_chat_id is None

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


class TestSettingsFromEnvironment:
    """Tests for settings loaded from environment variables."""

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

    def test_telegram_admin_chat_id_from_env(self):
        """Test that telegram_admin_chat_id is loaded from environment."""
        with patch.dict(os.environ, {"TELEGRAM_ADMIN_CHAT_ID": "123456789"}):
            settings = Settings()
            assert settings.telegram_admin_chat_id == "123456789"

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


class TestSettingsValidation:
    """Tests for settings validation."""

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

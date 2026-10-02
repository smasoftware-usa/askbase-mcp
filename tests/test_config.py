"""Tests for configuration management."""

import os
import pytest
from unittest.mock import patch


def test_settings_loads_from_env():
    """Test that settings loads from environment variables."""
    # Clear any polluted env vars, then set only what we want
    env = {
        "ASK_API_KEY": "ask_live_test123456789012345678901234",
    }
    # Remove ASK_API_BASE_URL if set by other tests
    with patch.dict(os.environ, env, clear=False):
        os.environ.pop("ASK_API_BASE_URL", None)
        from askbase_mcp.config import Settings
        settings = Settings()
        assert settings.api_key == "ask_live_test123456789012345678901234"
        assert settings.api_base_url == "https://api.askbase.co"
        assert settings.default_top_k == 5


def test_settings_validates_api_key():
    """Test that settings validates API key format."""
    with patch.dict(os.environ, {"ASK_API_KEY": "invalid_key"}):
        from askbase_mcp.config import Settings
        with pytest.raises(ValueError, match="should start with"):
            Settings()


def test_settings_strips_trailing_slash_from_url():
    """Test that trailing slash is removed from base URL."""
    with patch.dict(os.environ, {
        "ASK_API_KEY": "ask_live_test123456789012345678901234",
        "ASK_API_BASE_URL": "https://api.example.com/"
    }):
        from askbase_mcp.config import Settings
        settings = Settings()
        assert settings.api_base_url == "https://api.example.com"

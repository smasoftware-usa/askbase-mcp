"""Configuration management for ASKbase MCP server."""

import re
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """ASKbase MCP server configuration.

    All settings can be configured via environment variables prefixed with ASK_.
    """

    model_config = {"env_prefix": "ASK_"}

    # Required
    api_key: str = Field(
        ...,
        description="ASK-base API key (format: ask_live_xxx)",
    )

    # API connection
    api_base_url: str = Field(
        default="https://api.askbase.com",
        description="ASK-base API base URL",
    )

    # Defaults for search
    default_collection_id: Optional[UUID] = Field(
        default=None,
        description="Default collection ID for searches",
    )
    default_top_k: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Default number of search results",
    )
    default_similarity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Default similarity threshold for search",
    )

    # Server metadata
    server_name: str = "askbase-mcp"
    server_version: str = "1.0.0"

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key format."""
        if not v:
            raise ValueError("API key is required")
        if not re.match(r"^ask_live_[a-zA-Z0-9]{30}$", v):
            # Allow flexibility but warn about format
            if not v.startswith("ask_"):
                raise ValueError(
                    "API key should start with 'ask_live_'. "
                    "Get your API key from your ASK-base dashboard."
                )
        return v

    @field_validator("api_base_url")
    @classmethod
    def validate_api_base_url(cls, v: str) -> str:
        """Ensure URL doesn't have trailing slash."""
        return v.rstrip("/")


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

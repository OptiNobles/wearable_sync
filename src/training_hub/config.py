"""Application settings loaded from environment variables (and .env locally)."""

from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from training_hub.sources.polar.client import DEFAULT_BASE_URL as POLAR_DEFAULT_BASE_URL


class Settings(BaseSettings):
    # env_ignore_empty: an empty variable (e.g. POLAR_ACCESS_TOKEN=) counts as unset.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # Comma-separated in env, e.g. ENABLED_SOURCES=polar,garmin
    enabled_sources: Annotated[list[str], NoDecode, Field(min_length=1)] = ["polar"]
    # Polar keeps ~30 days of data, so each run re-reads the whole window.
    lookback_days: Annotated[int, Field(ge=1)] = 30
    local_sink_root: Path = Path("data")

    # Optional here; required only when the source is enabled (see registry).
    polar_access_token: SecretStr | None = None
    polar_base_url: str = POLAR_DEFAULT_BASE_URL

    @field_validator("enabled_sources", mode="before")
    @classmethod
    def _split_and_deduplicate(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = [name.strip() for name in value.split(",") if name.strip()]
        if isinstance(value, list):
            # dict.fromkeys keeps the first occurrence and the original order.
            value = list(dict.fromkeys(value))
        return value

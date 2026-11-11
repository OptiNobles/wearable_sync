"""Application settings loaded from environment variables (and .env locally)."""

from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from training_hub.core.models import UnityCatalogName
from training_hub.sources.polar.client import DEFAULT_BASE_URL as POLAR_DEFAULT_BASE_URL


class Settings(BaseSettings):
    # env_ignore_empty: an empty variable (e.g. POLAR_ACCESS_TOKEN=) counts as unset.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    # Comma-separated in env, e.g. ENABLED_SOURCES=polar,garmin
    enabled_sources: Annotated[list[str], NoDecode, Field(min_length=1)] = ["polar"]
    # Polar keeps ~30 days of data, so each run re-reads the whole window.
    lookback_days: Annotated[int, Field(ge=1)] = 30

    sink: Literal["local", "databricks"] = "local"
    local_sink_root: Path = Path("data")

    # Databricks: required only when SINK=databricks (checked below).
    databricks_host: str | None = None
    databricks_client_id: str | None = None
    databricks_client_secret: SecretStr | None = None
    # Files land in /Volumes/{catalog}/{source}/{volume}/...
    databricks_catalog: UnityCatalogName = "training_bronze"
    databricks_volume: UnityCatalogName = "files"

    # Polar: optional here; required only when the source is enabled (see registry).
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

    @model_validator(mode="after")
    def _require_databricks_credentials(self) -> Self:
        if self.sink != "databricks":
            return self
        missing = [
            name
            for name, value in (
                ("DATABRICKS_HOST", self.databricks_host),
                ("DATABRICKS_CLIENT_ID", self.databricks_client_id),
                ("DATABRICKS_CLIENT_SECRET", self.databricks_client_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"SINK=databricks requires: {', '.join(missing)}")
        return self

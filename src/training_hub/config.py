"""Application settings loaded from environment variables (and .env locally)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from training_hub.sources.polar.client import DEFAULT_BASE_URL as POLAR_DEFAULT_BASE_URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    polar_access_token: SecretStr
    polar_base_url: str = POLAR_DEFAULT_BASE_URL

"""Application settings loaded from environment variables (and .env locally)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    polar_access_token: SecretStr
    polar_base_url: str = "https://www.polaraccesslink.com"

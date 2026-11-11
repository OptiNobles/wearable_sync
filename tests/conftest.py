from collections.abc import Callable

import pytest

from wearable_sync.config import Settings

# Settings that a developer may have exported locally; tests must not depend on them.
SETTINGS_ENV_VARS = (
    "SINK",
    "DATABRICKS_HOST",
    "DATABRICKS_AUTH",
    "AZURE_CLIENT_ID",
    "DATABRICKS_CATALOG",
    "DATABRICKS_VOLUME",
)


@pytest.fixture
def make_settings(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Settings]:
    """Builds Settings from explicit overrides only: no .env file, no exported settings."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    def build(**overrides: object) -> Settings:
        return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]

    return build

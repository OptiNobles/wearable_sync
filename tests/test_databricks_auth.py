from collections.abc import Callable
from typing import Any, cast

import pytest
from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError
from databricks.sdk import config as sdk_config
from databricks.sdk.config import Config

from wearable_sync.config import Settings
from wearable_sync.sinks import databricks_auth, factory
from wearable_sync.sinks.databricks_auth import (
    AZURE_DATABRICKS_SCOPE,
    ManagedIdentityCredentials,
)

HOST = "https://adb-0000000000000000.0.azuredatabricks.net"
CLIENT_ID = "00000000-0000-0000-0000-000000000001"

MakeSettings = Callable[..., Settings]


class FakeCredential:
    """Stand-in for azure.identity.ManagedIdentityCredential (no network)."""

    def __init__(self, client_id: str | None = None, *, fail: bool = False) -> None:
        self.client_id = client_id
        self.fail = fail
        self.scopes: list[tuple[str, ...]] = []

    def get_token(self, *scopes: str, **kwargs: Any) -> AccessToken:
        self.scopes.append(scopes)
        if self.fail:
            raise ClientAuthenticationError("identity not assigned")
        return AccessToken("entra-token", 4_102_444_800)


@pytest.fixture
def fake_managed_identity(monkeypatch: pytest.MonkeyPatch) -> list[FakeCredential]:
    """Replaces ManagedIdentityCredential and records every credential created."""
    created: list[FakeCredential] = []

    def create(*, client_id: str) -> FakeCredential:
        credential = FakeCredential(client_id)
        created.append(credential)
        return credential

    monkeypatch.setattr(databricks_auth, "ManagedIdentityCredential", create)
    return created


@pytest.fixture
def no_host_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real Config fetches host metadata over the network (with ~5 minutes of
    retries for an unreachable host); the SDK falls back to explicit settings when
    that fails, so failing it immediately keeps tests offline and fast."""

    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise ConnectionError("offline test")

    monkeypatch.setattr(sdk_config, "get_host_metadata", unavailable)


def managed_identity_settings(make_settings: MakeSettings) -> Settings:
    return make_settings(
        sink="databricks",
        databricks_host=HOST,
        databricks_auth="managed-identity",
        azure_client_id=CLIENT_ID,
    )


def test_managed_identity_sends_entra_token_for_azure_databricks() -> None:
    credential = FakeCredential()
    # The strategy does not read the config, so it is called directly here.
    provider = ManagedIdentityCredentials(credential)(cast(Config, None))

    headers = provider()

    assert headers == {"Authorization": "Bearer entra-token"}
    assert credential.scopes == [(AZURE_DATABRICKS_SCOPE,)]


def test_managed_identity_uses_the_configured_client_id(
    fake_managed_identity: list[FakeCredential],
) -> None:
    ManagedIdentityCredentials.for_client_id(CLIENT_ID)

    assert [credential.client_id for credential in fake_managed_identity] == [CLIENT_ID]


def test_verify_turns_missing_identity_into_one_clear_error() -> None:
    strategy = ManagedIdentityCredentials(FakeCredential(fail=True))

    with pytest.raises(RuntimeError, match="AZURE_CLIENT_ID"):
        strategy.verify()


@pytest.mark.usefixtures("no_host_metadata")
def test_factory_builds_real_config_with_managed_identity(
    fake_managed_identity: list[FakeCredential], make_settings: MakeSettings
) -> None:
    config = factory.build_databricks_config(managed_identity_settings(make_settings))

    assert config.auth_type == "azure-managed-identity"
    assert config.authenticate() == {"Authorization": "Bearer entra-token"}
    # One token fetched up front by verify(), one for the request headers.
    assert len(fake_managed_identity[0].scopes) == 2


@pytest.mark.usefixtures("no_host_metadata")
def test_managed_identity_ignores_other_credentials_in_environment(
    monkeypatch: pytest.MonkeyPatch,
    fake_managed_identity: list[FakeCredential],
    make_settings: MakeSettings,
) -> None:
    settings = managed_identity_settings(make_settings)
    # Two different auth methods in the environment would make the SDK reject an
    # ambiguous configuration unless the auth type is explicit.
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-unused")
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "unused")
    monkeypatch.setenv("DATABRICKS_CLIENT_SECRET", "unused")

    config = factory.build_databricks_config(settings)

    assert config.authenticate() == {"Authorization": "Bearer entra-token"}


def test_factory_fails_fast_when_identity_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, make_settings: MakeSettings
) -> None:
    monkeypatch.setattr(
        databricks_auth,
        "ManagedIdentityCredential",
        lambda *, client_id: FakeCredential(client_id, fail=True),
    )

    with pytest.raises(RuntimeError, match="Managed identity could not get a token"):
        factory.build_databricks_config(managed_identity_settings(make_settings))


def test_factory_uses_azure_cli_with_explicit_auth_type(
    monkeypatch: pytest.MonkeyPatch, make_settings: MakeSettings
) -> None:
    # A real azure-cli Config would run `az`, so Config is replaced here.
    captured: dict[str, Any] = {}
    monkeypatch.setattr(factory, "Config", lambda **kwargs: captured.update(kwargs))
    settings = make_settings(sink="databricks", databricks_host=HOST)

    factory.build_databricks_config(settings)

    assert captured["auth_type"] == "azure-cli"
    assert "credentials_strategy" not in captured

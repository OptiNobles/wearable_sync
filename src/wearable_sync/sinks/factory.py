"""Builds the sink selected by the SINK setting."""

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

from wearable_sync.config import Settings
from wearable_sync.core.interfaces import Sink
from wearable_sync.sinks.databricks_auth import ManagedIdentityCredentials
from wearable_sync.sinks.databricks_volume import DatabricksVolumeSink
from wearable_sync.sinks.local import LocalFileSink


def build_sink(settings: Settings) -> Sink:
    if settings.sink == "local":
        return LocalFileSink(settings.local_sink_root)
    client = WorkspaceClient(config=build_databricks_config(settings))
    return DatabricksVolumeSink(
        client.files,
        catalog=settings.databricks_catalog,
        volume=settings.databricks_volume,
    )


def build_databricks_config(settings: Settings) -> Config:
    # The experimental files client calls extra endpoints that a plain file upload
    # does not need; the standard client is enough for small JSON files.
    common = {"host": settings.databricks_host, "disable_experimental_files_api_client": True}

    if settings.databricks_auth == "azure-cli":
        # Explicit auth type: never mix in other credentials the SDK may find in the
        # environment (e.g. DATABRICKS_TOKEN or a config profile).
        return Config(auth_type="azure-cli", **common)

    # The Python SDK has no managed identity strategy, so tokens come from azure-identity.
    # Settings validation guarantees the client ID; this check only narrows the type.
    if settings.azure_client_id is None:
        raise ValueError("DATABRICKS_AUTH=managed-identity requires: AZURE_CLIENT_ID")
    credentials = ManagedIdentityCredentials.for_client_id(settings.azure_client_id)
    # The SDK only authenticates on the first request; fail before any sync work starts.
    credentials.verify()
    return Config(
        credentials_strategy=credentials,
        # Explicit auth type for the same reason as above: other credentials found in
        # the environment must not make the SDK reject the configuration as ambiguous.
        auth_type=credentials.auth_type(),
        **common,
    )

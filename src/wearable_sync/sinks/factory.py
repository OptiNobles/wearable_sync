"""Builds the sink selected by the SINK setting."""

from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

from wearable_sync.config import Settings
from wearable_sync.core.interfaces import Sink
from wearable_sync.sinks.databricks_volume import DatabricksVolumeSink
from wearable_sync.sinks.local import LocalFileSink

# The sink only uploads files. The OAuth secret is restricted to this scope,
# so the token request must ask for it explicitly (the SDK default is all-apis).
DATABRICKS_SCOPES = ["files"]


def build_sink(settings: Settings) -> Sink:
    if settings.sink == "local":
        return LocalFileSink(settings.local_sink_root)
    return _build_databricks_sink(settings)


def _build_databricks_sink(settings: Settings) -> Sink:
    # Settings validation guarantees the credentials for SINK=databricks;
    # this check only narrows the type (an assert would vanish under python -O).
    secret = settings.databricks_client_secret
    if secret is None:
        raise ValueError("SINK=databricks requires: DATABRICKS_CLIENT_SECRET")

    config = Config(
        host=settings.databricks_host,
        client_id=settings.databricks_client_id,
        client_secret=secret.get_secret_value(),
        # Explicit auth type: never mix in other credentials the SDK may find
        # in the environment (e.g. DATABRICKS_TOKEN or a config profile).
        auth_type="oauth-m2m",
        scopes=DATABRICKS_SCOPES,
        # The experimental files client calls an extra endpoint outside the
        # 'files' scope; the standard client is enough for small JSON files.
        disable_experimental_files_api_client=True,
    )
    client = WorkspaceClient(config=config)
    return DatabricksVolumeSink(
        client.files,
        catalog=settings.databricks_catalog,
        volume=settings.databricks_volume,
    )

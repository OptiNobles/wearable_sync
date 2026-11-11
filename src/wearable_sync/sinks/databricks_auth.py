"""Managed identity authentication for the Databricks SDK.

The Python Databricks SDK supports Azure CLI login but not managed identities.
azure-identity does (including the Container Apps identity endpoint), so this module
plugs its tokens into the SDK as a custom credentials strategy.

Scope: Microsoft Entra ID tokens for Azure Databricks cannot be narrowed to Databricks
OAuth scopes (such as 'files'). What the identity can do is limited by its Unity Catalog
grants (read/write on the bronze volume only) and its workspace entitlements.
"""

from typing import Self

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ManagedIdentityCredential
from databricks.sdk.config import Config
from databricks.sdk.credentials_provider import CredentialsProvider, CredentialsStrategy

# Well-known Microsoft Entra application ID of the Azure Databricks service:
# tokens for this resource are accepted by every Azure Databricks workspace.
AZURE_DATABRICKS_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"

AUTH_TYPE = "azure-managed-identity"


class ManagedIdentityCredentials(CredentialsStrategy):
    def __init__(self, credential: TokenCredential) -> None:
        self._credential = credential

    @classmethod
    def for_client_id(cls, client_id: str) -> Self:
        """User-assigned managed identity with the given client (application) ID."""
        return cls(ManagedIdentityCredential(client_id=client_id))

    def auth_type(self) -> str:
        return AUTH_TYPE

    def verify(self) -> None:
        """Fetches a token once, so a missing identity fails fast with one clear error."""
        try:
            self._credential.get_token(AZURE_DATABRICKS_SCOPE)
        except ClientAuthenticationError as error:
            raise RuntimeError(
                "Managed identity could not get a token for Azure Databricks; "
                "check that the identity is assigned and AZURE_CLIENT_ID is its client ID"
            ) from error

    def __call__(self, cfg: Config) -> CredentialsProvider:
        def headers() -> dict[str, str]:
            # azure-identity caches the token and refreshes it before it expires.
            token = self._credential.get_token(AZURE_DATABRICKS_SCOPE)
            return {"Authorization": f"Bearer {token.token}"}

        return headers

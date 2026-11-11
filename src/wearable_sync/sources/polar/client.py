"""Thin HTTP client for the Polar AccessLink API v3.

Returns raw JSON only; mapping to RawRecord happens in source.py.
"""

import ssl
from types import TracebackType
from typing import Any, Self

import httpx
import truststore
from pydantic import SecretStr

DEFAULT_BASE_URL = "https://www.polaraccesslink.com"
DEFAULT_TIMEOUT_SECONDS = 60.0


class PolarClient:
    def __init__(
        self,
        access_token: SecretStr,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # Use the OS certificate store, so TLS works behind antivirus HTTPS
        # inspection locally and with system CAs inside the container.
        ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._http = httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {access_token.get_secret_value()}",
                "Accept": "application/json",
            },
            timeout=timeout,
            verify=ssl_context,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def list_exercises(
        self,
        *,
        samples: bool = False,
        zones: bool = False,
        route: bool = False,
    ) -> list[dict[str, Any]]:
        """Exercises uploaded to Polar Flow in the last 30 days."""
        params = {
            "samples": str(samples).lower(),
            "zones": str(zones).lower(),
            "route": str(route).lower(),
        }
        return self._get("/v3/exercises", params=params) or []

    def get_physical_info(self) -> dict[str, Any] | None:
        """Current physical info (weight, VO2max, resting HR, ...)."""
        return self._get("/v3/users/physical-info")

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = self._http.get(path, params=params)
        response.raise_for_status()
        if response.status_code == httpx.codes.NO_CONTENT:
            return None
        return response.json()

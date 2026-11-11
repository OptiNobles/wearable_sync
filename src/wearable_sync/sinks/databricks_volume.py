"""Sink uploading records as JSON files to Unity Catalog volumes."""

import io
from collections.abc import Iterable
from typing import Any, BinaryIO, Protocol

from databricks.sdk.errors import AlreadyExists, NotFound

from wearable_sync.core.models import RawRecord
from wearable_sync.sinks.layout import serialize, source_relative_path


class VolumeFiles(Protocol):
    """The part of databricks.sdk FilesAPI this sink uses (eases testing)."""

    def get_metadata(self, file_path: str) -> Any: ...

    def upload(
        self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None
    ) -> None: ...


class DatabricksVolumeSink:
    """Writes each record to /Volumes/{catalog}/{source}/{volume}/{data_type}/{date}/{id}.json

    Each source has its own schema in the catalog (e.g. wearable_sync_bronze.polar),
    holding a volume with the same name for every source (e.g. files).
    """

    def __init__(self, files: VolumeFiles, catalog: str, volume: str) -> None:
        self._files = files
        self._catalog = catalog
        self._volume = volume

    def write(self, records: Iterable[RawRecord]) -> int:
        """Upload records that are not stored yet; return how many were new."""
        written = 0
        for record in records:
            path = self.path_for(record)
            # Check first with a lightweight HEAD request. Relying only on
            # overwrite=False does not work for large files: the server rejects
            # the upload before reading the whole body and drops the connection,
            # which the SDK treats as a network error and retries for minutes.
            # It also avoids re-sending ~30 days of exercises on every run.
            if self._exists(path):
                continue
            try:
                # overwrite=False still guards against a concurrent writer.
                self._files.upload(path, io.BytesIO(serialize(record)), overwrite=False)
            except AlreadyExists:
                continue
            written += 1
        return written

    def path_for(self, record: RawRecord) -> str:
        return (
            f"/Volumes/{self._catalog}/{record.source}/{self._volume}/"
            f"{source_relative_path(record)}"
        )

    def _exists(self, path: str) -> bool:
        try:
            self._files.get_metadata(path)
        except NotFound:
            return False
        return True

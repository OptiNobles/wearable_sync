"""Sink writing records as JSON files to a local directory."""

from collections.abc import Iterable
from pathlib import Path

from wearable_sync.core.models import RawRecord
from wearable_sync.sinks.layout import record_path, serialize


class LocalFileSink:
    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, records: Iterable[RawRecord]) -> int:
        """Write records that are not stored yet; return how many were new."""
        written = 0
        for record in records:
            path = self._root / record_path(record)
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write to a temp file and rename, so an interrupted run never
            # leaves a half-written file that would later count as existing.
            tmp_path = path.with_name(path.name + ".tmp")
            try:
                tmp_path.write_bytes(serialize(record))
                tmp_path.replace(path)
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
            written += 1
        return written

"""Storage layout shared by all sinks: where a record goes and how it is serialized.

Path safety of source and record_id is guaranteed by RawRecord validation.
"""

from datetime import timezone
from pathlib import PurePosixPath

from training_hub.core.models import RawRecord


def record_path(record: RawRecord) -> PurePosixPath:
    """Relative path: {source}/{data_type}/{utc_date}/{record_id}.json"""
    return PurePosixPath(record.source) / source_relative_path(record)


def source_relative_path(record: RawRecord) -> PurePosixPath:
    """Path within a source's storage: {data_type}/{utc_date}/{record_id}.json"""
    utc_date = record.recorded_at.astimezone(timezone.utc).date().isoformat()
    return PurePosixPath(record.data_type, utc_date, f"{record.record_id}.json")


def serialize(record: RawRecord) -> bytes:
    """Whole envelope (metadata + untouched payload) as UTF-8 JSON."""
    return record.model_dump_json(indent=2).encode("utf-8")

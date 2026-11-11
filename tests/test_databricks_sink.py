from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO

import pytest
from databricks.sdk.errors import AlreadyExists, NotFound, PermissionDenied
from pydantic import ValidationError

from wearable_sync.config import Settings
from wearable_sync.core.interfaces import Sink
from wearable_sync.core.models import DataType, RawRecord
from wearable_sync.sinks.databricks_volume import DatabricksVolumeSink
from wearable_sync.sinks.factory import build_sink
from wearable_sync.sinks.local import LocalFileSink


class FakeFiles:
    """In-memory stand-in for databricks.sdk FilesAPI (get_metadata + upload)."""

    def __init__(self) -> None:
        self.stored: dict[str, bytes] = {}
        self.overwrite_flags: list[bool | None] = []
        self.uploads: list[str] = []

    def get_metadata(self, file_path: str) -> object:
        if file_path not in self.stored:
            raise NotFound(f"{file_path} not found")
        return object()

    def upload(self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None) -> None:
        self.uploads.append(file_path)
        self.overwrite_flags.append(overwrite)
        if file_path in self.stored and overwrite is False:
            raise AlreadyExists("The file being created already exists.")
        self.stored[file_path] = contents.read()


def make_record(
    record_id: str = "EXAMPLE_RUN_1",
    recorded_at: datetime = datetime(2026, 11, 2, 7, 2, 18, tzinfo=timezone.utc),
) -> RawRecord:
    return RawRecord(
        source="polar",
        data_type=DataType.EXERCISE,
        record_id=record_id,
        recorded_at=recorded_at,
        payload={"sport": "RUNNING"},
    )


def make_sink(files: FakeFiles) -> DatabricksVolumeSink:
    return DatabricksVolumeSink(files, catalog="wearable_sync_bronze", volume="files")


def test_databricks_sink_fulfils_sink_contract() -> None:
    sink: Sink = make_sink(FakeFiles())

    assert sink.write([]) == 0


def test_record_is_uploaded_to_source_schema_volume_path() -> None:
    files = FakeFiles()

    make_sink(files).write([make_record()])

    assert list(files.stored) == [
        "/Volumes/wearable_sync_bronze/polar/files/exercise/2026-11-02/EXAMPLE_RUN_1.json"
    ]


def test_uploaded_file_contains_whole_envelope() -> None:
    files = FakeFiles()
    record = make_record()

    make_sink(files).write([record])

    (content,) = files.stored.values()
    assert RawRecord.model_validate_json(content) == record


def test_date_folder_uses_utc() -> None:
    files = FakeFiles()
    late_evening_utc = datetime(2026, 11, 2, 0, 30, tzinfo=timezone(timedelta(hours=2)))

    make_sink(files).write([make_record(recorded_at=late_evening_utc)])

    assert "/exercise/2026-11-01/" in next(iter(files.stored))


def test_uploads_never_overwrite() -> None:
    files = FakeFiles()

    make_sink(files).write([make_record("A"), make_record("B")])

    assert files.overwrite_flags == [False, False]


def test_existing_files_are_skipped_and_not_counted() -> None:
    files = FakeFiles()
    sink = make_sink(files)

    first = sink.write([make_record("A"), make_record("B")])
    second = sink.write([make_record("A"), make_record("B"), make_record("C")])

    assert (first, second) == (2, 1)
    assert len(files.stored) == 3


def test_existing_files_are_not_uploaded_again() -> None:
    files = FakeFiles()
    sink = make_sink(files)
    sink.write([make_record("A")])

    sink.write([make_record("A")])

    assert len(files.uploads) == 1


def test_concurrent_writer_conflict_is_treated_as_existing() -> None:
    class RacingFiles(FakeFiles):
        def get_metadata(self, file_path: str) -> object:
            raise NotFound("not there yet")  # another writer creates it in between

        def upload(
            self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None
        ) -> None:
            raise AlreadyExists("The file being created already exists.")

    assert make_sink(RacingFiles()).write([make_record()]) == 0


def test_other_errors_are_raised() -> None:
    class DenyingFiles(FakeFiles):
        def upload(
            self, file_path: str, contents: BinaryIO, *, overwrite: bool | None = None
        ) -> None:
            raise PermissionDenied("no WRITE VOLUME")

    with pytest.raises(PermissionDenied):
        DatabricksVolumeSink(DenyingFiles(), catalog="wearable_sync_bronze", volume="files").write(
            [make_record()]
        )


MakeSettings = Callable[..., Settings]


def test_factory_builds_local_sink_by_default(tmp_path: Path, make_settings: MakeSettings) -> None:
    sink = build_sink(make_settings(local_sink_root=tmp_path))

    assert isinstance(sink, LocalFileSink)


def test_databricks_sink_requires_host(make_settings: MakeSettings) -> None:
    with pytest.raises(ValidationError, match="requires: DATABRICKS_HOST"):
        make_settings(sink="databricks")


def test_azure_cli_auth_is_the_default_and_needs_no_client_id(make_settings: MakeSettings) -> None:
    settings = make_settings(sink="databricks", databricks_host="https://example.com")

    assert settings.databricks_auth == "azure-cli"


def test_managed_identity_auth_requires_client_id(make_settings: MakeSettings) -> None:
    with pytest.raises(ValidationError, match="AZURE_CLIENT_ID"):
        make_settings(
            sink="databricks",
            databricks_host="https://example.com",
            databricks_auth="managed-identity",
        )


def test_unknown_auth_mode_is_rejected(make_settings: MakeSettings) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            sink="databricks", databricks_host="https://example.com", databricks_auth="pat"
        )


def test_databricks_settings_are_not_required_for_local_sink(make_settings: MakeSettings) -> None:
    assert make_settings(sink="local").databricks_host is None


def test_unknown_sink_is_rejected(
    monkeypatch: pytest.MonkeyPatch, make_settings: MakeSettings
) -> None:
    monkeypatch.setenv("SINK", "s3")

    with pytest.raises(ValueError):
        make_settings()


@pytest.mark.parametrize("field", ["databricks_catalog", "databricks_volume"])
@pytest.mark.parametrize(
    "name", ["../escape", "wearable_sync.bronze", "Wearable_Sync_Bronze", "my-volume"]
)
def test_invalid_catalog_or_volume_name_is_rejected(
    field: str, name: str, make_settings: MakeSettings
) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: name})

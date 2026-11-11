from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO

import pytest
from databricks.sdk.errors import AlreadyExists, NotFound, PermissionDenied
from pydantic import ValidationError

from training_hub.config import Settings
from training_hub.core.interfaces import Sink
from training_hub.core.models import DataType, RawRecord
from training_hub.sinks.databricks_volume import DatabricksVolumeSink
from training_hub.sinks.factory import build_sink
from training_hub.sinks.local import LocalFileSink


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
    return DatabricksVolumeSink(files, catalog="training_bronze", volume="files")


def test_databricks_sink_fulfils_sink_contract() -> None:
    sink: Sink = make_sink(FakeFiles())

    assert sink.write([]) == 0


def test_record_is_uploaded_to_source_schema_volume_path() -> None:
    files = FakeFiles()

    make_sink(files).write([make_record()])

    assert list(files.stored) == [
        "/Volumes/training_bronze/polar/files/exercise/2026-11-02/EXAMPLE_RUN_1.json"
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
        DatabricksVolumeSink(DenyingFiles(), catalog="training_bronze", volume="files").write(
            [make_record()]
        )


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SINK",
        "DATABRICKS_HOST",
        "DATABRICKS_CLIENT_ID",
        "DATABRICKS_CLIENT_SECRET",
        "DATABRICKS_CATALOG",
        "DATABRICKS_VOLUME",
    ):
        monkeypatch.delenv(name, raising=False)


def test_factory_builds_local_sink_by_default(tmp_path: Path) -> None:
    sink = build_sink(make_settings(local_sink_root=tmp_path))

    assert isinstance(sink, LocalFileSink)


def test_databricks_sink_settings_report_all_missing_credentials() -> None:
    with pytest.raises(ValidationError, match="DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET"):
        make_settings(sink="databricks", databricks_host="https://example.com")


def test_databricks_credentials_are_not_required_for_local_sink() -> None:
    assert make_settings(sink="local").databricks_host is None


def test_unknown_sink_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SINK", "s3")

    with pytest.raises(ValueError):
        make_settings()


@pytest.mark.parametrize("field", ["databricks_catalog", "databricks_volume"])
@pytest.mark.parametrize("name", ["../escape", "training.bronze", "Training_Bronze", "my-volume"])
def test_invalid_catalog_or_volume_name_is_rejected(field: str, name: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: name})

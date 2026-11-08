from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from training_hub.core.interfaces import Sink
from training_hub.core.models import DataType, RawRecord
from training_hub.sinks.local import LocalFileSink


def make_record(
    record_id: str = "EXAMPLE_RUN_1",
    recorded_at: datetime = datetime(2026, 11, 2, 7, 2, 18, tzinfo=timezone.utc),
) -> RawRecord:
    return RawRecord(
        source="polar",
        data_type=DataType.EXERCISE,
        record_id=record_id,
        recorded_at=recorded_at,
        payload={"sport": "RUNNING", "distance": 9942.0},
    )


def test_local_sink_fulfils_sink_contract(tmp_path: Path) -> None:
    sink: Sink = LocalFileSink(tmp_path)

    assert sink.write([]) == 0


def test_record_is_written_to_layout_path(tmp_path: Path) -> None:
    LocalFileSink(tmp_path).write([make_record()])

    assert (tmp_path / "polar" / "exercise" / "2026-11-02" / "EXAMPLE_RUN_1.json").is_file()


def test_written_file_contains_whole_envelope(tmp_path: Path) -> None:
    record = make_record()

    LocalFileSink(tmp_path).write([record])

    path = tmp_path / "polar" / "exercise" / "2026-11-02" / "EXAMPLE_RUN_1.json"
    assert RawRecord.model_validate_json(path.read_bytes()) == record


def test_date_folder_uses_utc(tmp_path: Path) -> None:
    # 00:30 at +02:00 is still the previous day in UTC.
    local_midnight_run = datetime(2026, 11, 2, 0, 30, tzinfo=timezone(timedelta(hours=2)))

    LocalFileSink(tmp_path).write([make_record(recorded_at=local_midnight_run)])

    assert (tmp_path / "polar" / "exercise" / "2026-11-01" / "EXAMPLE_RUN_1.json").is_file()


def test_existing_records_are_not_rewritten(tmp_path: Path) -> None:
    sink = LocalFileSink(tmp_path)

    first = sink.write([make_record("A"), make_record("B")])
    second = sink.write([make_record("A"), make_record("B"), make_record("C")])

    assert (first, second) == (2, 1)


def test_no_temp_files_are_left_behind(tmp_path: Path) -> None:
    LocalFileSink(tmp_path).write([make_record("A"), make_record("B")])

    assert list(tmp_path.rglob("*.tmp")) == []


def test_temp_file_is_removed_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_replace(self: Path, target: Path) -> Path:
        raise OSError("simulated failure")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated failure"):
        LocalFileSink(tmp_path).write([make_record()])

    assert list(tmp_path.rglob("*.tmp")) == []
    assert list(tmp_path.rglob("*.json")) == []

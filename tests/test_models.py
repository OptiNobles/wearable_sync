from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from training_hub.core.models import DataType, RawRecord

UNSAFE_IDENTIFIERS = ["../escape", "a/b", "a\\b", ".", "..", ".hidden", "", "08:02:32", "/abs"]


def make_record(source: str = "polar", record_id: str = "EXAMPLE_RUN_1") -> RawRecord:
    return RawRecord(
        source=source,
        data_type=DataType.EXERCISE,
        record_id=record_id,
        recorded_at=datetime(2026, 11, 2, 7, 2, 18, tzinfo=timezone.utc),
        payload={},
    )


@pytest.mark.parametrize("record_id", ["5ODQEXZ6", "ywLeL8kR", "20261108T080232Z", "a.b_c-d"])
def test_safe_record_id_is_accepted(record_id: str) -> None:
    assert make_record(record_id=record_id).record_id == record_id


@pytest.mark.parametrize("record_id", UNSAFE_IDENTIFIERS)
def test_unsafe_record_id_is_rejected(record_id: str) -> None:
    with pytest.raises(ValidationError):
        make_record(record_id=record_id)


@pytest.mark.parametrize("source", ["polar", "garmin", "polar_v2"])
def test_valid_source_is_accepted(source: str) -> None:
    assert make_record(source=source).source == source


# A source becomes a Unity Catalog schema name: no dots, dashes or uppercase.
@pytest.mark.parametrize(
    "source", [*UNSAFE_IDENTIFIERS, "Polar", "my-source", "a.b", "1polar", "_polar"]
)
def test_invalid_source_is_rejected(source: str) -> None:
    with pytest.raises(ValidationError):
        make_record(source=source)


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RawRecord(
            source="polar",
            data_type=DataType.EXERCISE,
            record_id="EXAMPLE_RUN_1",
            recorded_at=datetime(2026, 11, 2, 7, 2, 18),
            payload={},
        )


def test_record_is_immutable() -> None:
    record = make_record()

    with pytest.raises(ValidationError):
        record.record_id = "OTHER"  # type: ignore[misc]

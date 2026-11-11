from collections.abc import Iterable, Iterator
from datetime import date, datetime, timezone

from training_hub.core.models import DataType, RawRecord
from training_hub.services.sync import SyncResult, sync

SINCE = date(2026, 1, 1)


def make_record(source: str, data_type: DataType, record_id: str) -> RawRecord:
    return RawRecord(
        source=source,
        data_type=data_type,
        record_id=record_id,
        recorded_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
        payload={},
    )


class FakeSource:
    """Source returning predefined records; listed data types raise instead."""

    def __init__(
        self,
        name: str,
        records: dict[DataType, list[RawRecord]],
        failing: frozenset[DataType] = frozenset(),
    ) -> None:
        self.name = name
        self.supported_types = frozenset(records) | failing
        self._records = records
        self._failing = failing
        self.fetch_calls: list[tuple[DataType, date]] = []

    def fetch(self, data_type: DataType, since: date) -> Iterator[RawRecord]:
        self.fetch_calls.append((data_type, since))
        if data_type in self._failing:
            raise RuntimeError(f"{self.name} {data_type} unavailable")
        return iter(self._records[data_type])


class FakeSink:
    def __init__(self) -> None:
        self.records: list[RawRecord] = []

    def write(self, records: Iterable[RawRecord]) -> int:
        batch = list(records)
        self.records.extend(batch)
        return len(batch)


def test_all_types_of_all_sources_are_synced() -> None:
    polar = FakeSource(
        "polar",
        {
            DataType.EXERCISE: [make_record("polar", DataType.EXERCISE, "E1")],
            DataType.BODY_MEASUREMENT: [make_record("polar", DataType.BODY_MEASUREMENT, "B1")],
        },
    )
    other = FakeSource("other", {DataType.EXERCISE: [make_record("other", DataType.EXERCISE, "X1")]})
    sink = FakeSink()

    report = sync([polar, other], sink, SINCE)

    assert report.succeeded
    assert report.total_new_records == 3
    assert {(r.source, r.record_id) for r in sink.records} == {
        ("polar", "E1"),
        ("polar", "B1"),
        ("other", "X1"),
    }


def test_since_is_passed_to_every_fetch() -> None:
    source = FakeSource("polar", {DataType.EXERCISE: [], DataType.BODY_MEASUREMENT: []})

    sync([source], FakeSink(), SINCE)

    assert {since for _, since in source.fetch_calls} == {SINCE}


def test_failure_of_one_type_does_not_block_others() -> None:
    polar = FakeSource(
        "polar",
        {DataType.EXERCISE: [make_record("polar", DataType.EXERCISE, "E1")]},
        failing=frozenset({DataType.BODY_MEASUREMENT}),
    )
    sink = FakeSink()

    report = sync([polar], sink, SINCE)

    assert not report.succeeded
    assert [r.record_id for r in sink.records] == ["E1"]
    assert report.failures == (
        SyncResult(
            "polar",
            DataType.BODY_MEASUREMENT,
            error="RuntimeError: polar body_measurement unavailable",
        ),
    )


def test_failure_of_one_source_does_not_block_others() -> None:
    broken = FakeSource("broken", {}, failing=frozenset({DataType.EXERCISE}))
    polar = FakeSource("polar", {DataType.EXERCISE: [make_record("polar", DataType.EXERCISE, "E1")]})
    sink = FakeSink()

    report = sync([broken, polar], sink, SINCE)

    assert [r.record_id for r in sink.records] == ["E1"]
    assert [f.source for f in report.failures] == ["broken"]


def test_report_counts_new_records_per_source_and_type() -> None:
    polar = FakeSource(
        "polar",
        {
            DataType.EXERCISE: [
                make_record("polar", DataType.EXERCISE, "E1"),
                make_record("polar", DataType.EXERCISE, "E2"),
            ],
            DataType.BODY_MEASUREMENT: [],
        },
    )

    report = sync([polar], FakeSink(), SINCE)

    counts = {(r.source, r.data_type): r.new_records for r in report.results}
    assert counts == {
        ("polar", DataType.EXERCISE): 2,
        ("polar", DataType.BODY_MEASUREMENT): 0,
    }

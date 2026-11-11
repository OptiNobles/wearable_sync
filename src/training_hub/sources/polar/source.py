"""Polar AccessLink adapter: turns raw API responses into RawRecords."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from typing import Any

from training_hub.core.models import DataType, RawRecord
from training_hub.sources.polar.client import PolarClient

SOURCE_NAME = "polar"


class PolarSource:
    name = SOURCE_NAME
    supported_types = frozenset({DataType.EXERCISE, DataType.BODY_MEASUREMENT})

    def __init__(self, client: PolarClient) -> None:
        self._client = client

    def fetch(self, data_type: DataType, since: date) -> list[RawRecord]:
        # Everything happens here, eagerly: HTTP and validation errors surface
        # at fetch(), before a sink writes anything, and the returned records
        # stay usable after the client is closed.
        if data_type == DataType.EXERCISE:
            exercises = self._client.list_exercises(samples=True, zones=True, route=True)
            return list(_exercise_records(exercises, since))
        if data_type == DataType.BODY_MEASUREMENT:
            info = self._client.get_physical_info()
            return list(_body_measurement_records(info, since))
        raise ValueError(f"{SOURCE_NAME} does not support data type: {data_type}")


def _exercise_records(exercises: list[dict[str, Any]], since: date) -> Iterator[RawRecord]:
    for exercise in exercises:
        started_at = _exercise_start(exercise)
        if started_at.date() < since:
            continue
        yield RawRecord(
            source=SOURCE_NAME,
            data_type=DataType.EXERCISE,
            record_id=str(exercise["id"]),
            recorded_at=started_at,
            payload=exercise,
        )


def _body_measurement_records(info: dict[str, Any] | None, since: date) -> Iterator[RawRecord]:
    # Polar exposes only the current state; 'modified' changes on every update,
    # so it identifies the measurement.
    if info is None:
        return
    modified_at = datetime.fromisoformat(info["modified"])
    if modified_at.date() < since:
        return
    yield RawRecord(
        source=SOURCE_NAME,
        data_type=DataType.BODY_MEASUREMENT,
        record_id=_utc_timestamp_id(modified_at),
        recorded_at=modified_at,
        payload=info,
    )


def _exercise_start(exercise: dict[str, Any]) -> datetime:
    """Combine Polar's naive local start_time with its UTC offset (minutes)."""
    local_start = datetime.fromisoformat(exercise["start_time"])
    offset = timedelta(minutes=exercise["start_time_utc_offset"])
    return local_start.replace(tzinfo=timezone(offset))


def _utc_timestamp_id(moment: datetime) -> str:
    """Format-independent, filename-safe id, e.g. 20261108T080232Z."""
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

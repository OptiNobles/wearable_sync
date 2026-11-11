import json
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from wearable_sync.core.models import DataType
from wearable_sync.sources.polar.client import PolarClient
from wearable_sync.sources.polar.source import PolarSource

FIXTURES = Path(__file__).parent / "fixtures" / "polar"

Handler = Callable[[httpx.Request], httpx.Response]
SourceFactory = Callable[[Handler], PolarSource]


def load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def fixture_api(request: httpx.Request) -> httpx.Response:
    """Fake Polar API serving responses from fixture files."""
    if request.url.path == "/v3/exercises":
        return httpx.Response(200, json=load_fixture("exercises.json"))
    if request.url.path == "/v3/users/physical-info":
        return httpx.Response(200, json=load_fixture("physical_info.json"))
    return httpx.Response(404)


def no_content_api(request: httpx.Request) -> httpx.Response:
    return httpx.Response(204)


def make_client(handler: Handler) -> PolarClient:
    return PolarClient(SecretStr("test-token"), transport=httpx.MockTransport(handler))


@pytest.fixture
def make_source() -> Iterator[SourceFactory]:
    """Build PolarSources on fake APIs and close their clients after the test."""
    clients: list[PolarClient] = []

    def factory(handler: Handler) -> PolarSource:
        client = make_client(handler)
        clients.append(client)
        return PolarSource(client)

    yield factory
    for client in clients:
        client.close()


def test_exercise_record_uses_vendor_id_and_timezone_aware_start(
    make_source: SourceFactory,
) -> None:
    records = list(make_source(fixture_api).fetch(DataType.EXERCISE, since=date(2026, 1, 1)))

    run = next(r for r in records if r.record_id == "EXAMPLE_RUN_1")
    assert run.source == "polar"
    assert run.data_type == DataType.EXERCISE
    assert run.recorded_at == datetime(
        2026, 11, 2, 7, 2, 18, tzinfo=timezone(timedelta(minutes=60))
    )


def test_exercise_payload_is_untouched(make_source: SourceFactory) -> None:
    records = list(make_source(fixture_api).fetch(DataType.EXERCISE, since=date(2026, 1, 1)))

    assert [r.payload for r in records] == load_fixture("exercises.json")


def test_exercises_before_since_are_skipped(make_source: SourceFactory) -> None:
    records = list(make_source(fixture_api).fetch(DataType.EXERCISE, since=date(2026, 11, 1)))

    assert [r.record_id for r in records] == ["EXAMPLE_RUN_1"]


def test_exercises_are_requested_with_samples_zones_and_route(
    make_source: SourceFactory,
) -> None:
    seen: list[httpx.Request] = []

    def recording_api(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return fixture_api(request)

    make_source(recording_api).fetch(DataType.EXERCISE, since=date(2026, 1, 1))

    params = seen[0].url.params
    assert params["samples"] == "true"
    assert params["zones"] == "true"
    assert params["route"] == "true"


def test_requests_send_bearer_token(make_source: SourceFactory) -> None:
    seen: list[httpx.Request] = []

    def recording_api(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return fixture_api(request)

    make_source(recording_api).fetch(DataType.EXERCISE, since=date(2026, 1, 1))

    assert seen[0].headers["Authorization"] == "Bearer test-token"


def test_body_measurement_uses_normalized_utc_id_and_timestamp(
    make_source: SourceFactory,
) -> None:
    records = list(
        make_source(fixture_api).fetch(DataType.BODY_MEASUREMENT, since=date(2026, 1, 1))
    )

    assert len(records) == 1
    record = records[0]
    assert record.record_id == "20261108T080232Z"
    assert record.recorded_at == datetime(2026, 11, 8, 8, 2, 32, tzinfo=timezone.utc)
    assert record.payload["weight"] == 80.0


def test_body_measurement_before_since_is_skipped(make_source: SourceFactory) -> None:
    records = list(
        make_source(fixture_api).fetch(DataType.BODY_MEASUREMENT, since=date(2026, 11, 9))
    )

    assert records == []


@pytest.mark.parametrize("data_type", [DataType.EXERCISE, DataType.BODY_MEASUREMENT])
def test_no_content_yields_no_records(make_source: SourceFactory, data_type: DataType) -> None:
    assert list(make_source(no_content_api).fetch(data_type, since=date(2026, 1, 1))) == []


def test_http_error_is_raised_at_fetch(make_source: SourceFactory) -> None:
    source = make_source(lambda request: httpx.Response(401))

    with pytest.raises(httpx.HTTPStatusError):
        source.fetch(DataType.EXERCISE, since=date(2026, 1, 1))


def test_invalid_record_fails_at_fetch_before_anything_is_returned(
    make_source: SourceFactory,
) -> None:
    def api_with_bad_id(request: httpx.Request) -> httpx.Response:
        exercises = load_fixture("exercises.json")
        exercises[1]["id"] = "bad/id"  # type: ignore[index]
        return httpx.Response(200, json=exercises)

    with pytest.raises(ValidationError):
        make_source(api_with_bad_id).fetch(DataType.EXERCISE, since=date(2026, 1, 1))


@pytest.mark.parametrize("data_type", [DataType.EXERCISE, DataType.BODY_MEASUREMENT])
def test_records_stay_usable_after_client_is_closed(data_type: DataType) -> None:
    with make_client(fixture_api) as client:
        records = PolarSource(client).fetch(data_type, since=date(2026, 1, 1))

    assert len(list(records)) >= 1

from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from wearable_sync.core.models import DataType, RawRecord
from wearable_sync.jobs import daily_sync


class FakeSource:
    name = "fake"
    supported_types = frozenset({DataType.EXERCISE, DataType.BODY_MEASUREMENT})

    def __init__(self, failing: frozenset[DataType] = frozenset()) -> None:
        self._failing = failing

    def fetch(self, data_type: DataType, since: date) -> list[RawRecord]:
        if data_type in self._failing:
            raise RuntimeError("unavailable")
        return [
            RawRecord(
                source=self.name,
                data_type=data_type,
                record_id="R1",
                recorded_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
                payload={},
            )
        ]


@pytest.fixture
def job_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run the job in an empty directory (no .env) with sink output in tmp_path."""
    monkeypatch.chdir(tmp_path)
    # main() patches ssl globally; keep the rest of the test session unaffected.
    monkeypatch.setattr(daily_sync.truststore, "inject_into_ssl", lambda: None)
    for name in ("ENABLED_SOURCES", "LOOKBACK_DAYS", "POLAR_ACCESS_TOKEN", "SINK"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOCAL_SINK_ROOT", str(tmp_path / "data"))
    yield tmp_path / "data"


def use_sources(monkeypatch: pytest.MonkeyPatch, *sources: Any) -> None:
    monkeypatch.setattr(daily_sync, "build_sources", lambda names, settings, stack: list(sources))


def test_successful_run_exits_zero_and_writes_records(
    job_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_sources(monkeypatch, FakeSource())

    assert daily_sync.main() == 0
    assert len(list(job_env.rglob("*.json"))) == 2


def test_failed_pair_exits_one_with_single_summary(
    job_env: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    use_sources(monkeypatch, FakeSource(failing=frozenset({DataType.BODY_MEASUREMENT})))

    assert daily_sync.main() == 1
    summaries = [r for r in caplog.records if "Sync finished with failures" in r.getMessage()]
    assert len(summaries) == 1
    assert "fake/body_measurement" in summaries[0].getMessage()


def test_configuration_error_is_logged_and_exits_one(
    job_env: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("ENABLED_SOURCES", "unknown")

    assert daily_sync.main() == 1
    assert any(r.getMessage() == "Sync aborted" for r in caplog.records)

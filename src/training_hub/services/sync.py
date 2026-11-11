"""Moves records from sources to a sink, isolating failures per (source, data type)."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from training_hub.core.interfaces import Sink, Source
from training_hub.core.models import DataType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    source: str
    data_type: DataType
    new_records: int = 0
    error: str | None = None


@dataclass(frozen=True)
class SyncReport:
    results: tuple[SyncResult, ...]

    @property
    def succeeded(self) -> bool:
        return all(result.error is None for result in self.results)

    @property
    def total_new_records(self) -> int:
        return sum(result.new_records for result in self.results)

    @property
    def failures(self) -> tuple[SyncResult, ...]:
        return tuple(result for result in self.results if result.error is not None)


def sync(sources: Iterable[Source], sink: Sink, since: date) -> SyncReport:
    """Sync every supported data type of every source into the sink.

    A failure in one (source, data type) pair is logged and reported,
    but does not stop the remaining pairs.
    """
    results: list[SyncResult] = []
    for source in sources:
        for data_type in sorted(source.supported_types):
            try:
                new_records = sink.write(source.fetch(data_type, since))
            except Exception as exc:
                # Never log payloads: they contain health data.
                logger.exception("Sync failed: source=%s data_type=%s", source.name, data_type)
                results.append(
                    SyncResult(source.name, data_type, error=f"{type(exc).__name__}: {exc}")
                )
                continue
            logger.info(
                "Synced: source=%s data_type=%s new_records=%d",
                source.name,
                data_type,
                new_records,
            )
            results.append(SyncResult(source.name, data_type, new_records=new_records))
    return SyncReport(tuple(results))

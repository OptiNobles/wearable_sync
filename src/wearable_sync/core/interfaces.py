"""Contracts that every data source and sink must fulfil."""

from collections.abc import Iterable
from datetime import date
from typing import Protocol

from wearable_sync.core.models import DataType, RawRecord


class Source(Protocol):
    """A provider of raw records, e.g. a wearable vendor API."""

    name: str
    supported_types: frozenset[DataType]

    def fetch(self, data_type: DataType, since: date) -> Iterable[RawRecord]:
        """Yield records of the given type available since the given date."""
        ...


class Sink(Protocol):
    """A destination for raw records, e.g. a Databricks Volume."""

    def write(self, records: Iterable[RawRecord]) -> int:
        """Persist records and return how many were written."""
        ...

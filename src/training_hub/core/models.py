"""Source-agnostic data models shared by all sources and sinks."""

from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict


class DataType(StrEnum):
    """Kind of data a source can provide."""

    EXERCISE = "exercise"
    BODY_MEASUREMENT = "body_measurement"


class RawRecord(BaseModel):
    """Envelope around an untouched vendor payload.

    The payload is stored as-is; normalization happens downstream in Databricks.
    """

    model_config = ConfigDict(frozen=True)

    source: str
    data_type: DataType
    record_id: str
    recorded_at: AwareDatetime
    payload: dict[str, Any]

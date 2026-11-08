"""Source-agnostic data models shared by all sources and sinks."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# Used as path segments by sinks: must start with a letter or digit (rules out
# "." and ".."), and may contain only letters, digits, ".", "_" and "-".
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]


class DataType(StrEnum):
    """Kind of data a source can provide."""

    EXERCISE = "exercise"
    BODY_MEASUREMENT = "body_measurement"


class RawRecord(BaseModel):
    """Envelope around an untouched vendor payload.

    The payload is stored as-is; normalization happens downstream in Databricks.
    """

    model_config = ConfigDict(frozen=True)

    source: SafeIdentifier
    data_type: DataType
    record_id: SafeIdentifier
    recorded_at: AwareDatetime
    payload: dict[str, Any]

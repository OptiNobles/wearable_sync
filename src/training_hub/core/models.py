"""Source-agnostic data models shared by all sources and sinks."""

from enum import StrEnum
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

# Used as file names by sinks: must start with a letter or digit (rules out
# "." and ".."), and may contain only letters, digits, ".", "_" and "-".
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]

# Used as Unity Catalog object names (catalog, schema, volume), e.g. a source
# name becomes a schema. Lowercase only: Unity Catalog stores names in lowercase,
# so "Polar" and "polar" would silently refer to the same schema.
UnityCatalogName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]


class DataType(StrEnum):
    """Kind of data a source can provide."""

    EXERCISE = "exercise"
    BODY_MEASUREMENT = "body_measurement"


class RawRecord(BaseModel):
    """Envelope around an untouched vendor payload.

    The payload is stored as-is; normalization happens downstream in Databricks.
    """

    model_config = ConfigDict(frozen=True)

    source: UnityCatalogName
    data_type: DataType
    record_id: SafeIdentifier
    recorded_at: AwareDatetime
    payload: dict[str, Any]

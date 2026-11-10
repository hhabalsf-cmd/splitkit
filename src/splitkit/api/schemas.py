"""Request models: every payload is validated here before touching the database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from splitkit.assignment import Variant, validate_variants
from splitkit.metrics.spec import EVENT_PATTERN, MetricSpec

KEY_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
VARIANT_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,31}$"
EVENT_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
MAX_BATCH = 1000
MAX_EVENT_AGE = timedelta(days=7)  # offline clients may flush late, but not this late
MAX_CLOCK_SKEW = timedelta(minutes=5)

UserId = Field(min_length=1, max_length=128)


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VariantIn(_Model):
    name: str = Field(pattern=VARIANT_PATTERN)
    weight: float = Field(gt=0, le=1)


class ExperimentCreate(_Model):
    key: str = Field(pattern=KEY_PATTERN)
    # v1 analyzes two-arm tests; assignment itself supports more
    variants: list[VariantIn] = Field(min_length=2, max_length=2)
    metrics: list[MetricSpec] = Field(min_length=1, max_length=20)
    salt: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")

    @model_validator(mode="after")
    def _check(self) -> ExperimentCreate:
        validate_variants(tuple(Variant(v.name, v.weight) for v in self.variants))
        names = [m.name for m in self.metrics]
        if len(set(names)) != len(names):
            raise ValueError("metric names must be unique")
        return self


class StatusUpdate(_Model):
    status: Literal["draft", "running", "stopped"]


class AssignRequest(_Model):
    experiment_key: str = Field(pattern=KEY_PATTERN)
    user_id: str = UserId


class ExposureIn(_Model):
    experiment_key: str = Field(pattern=KEY_PATTERN)
    user_id: str = UserId
    variant: str = Field(min_length=1, max_length=32)


class ExposureBatch(_Model):
    exposures: list[ExposureIn] = Field(min_length=1, max_length=MAX_BATCH)


class EventIn(_Model):
    event_id: str = Field(pattern=EVENT_ID_PATTERN)
    user_id: str = UserId
    event_name: str = Field(pattern=EVENT_PATTERN)
    value: float | None = Field(default=None, allow_inf_nan=False)
    ts: datetime | None = None

    @field_validator("ts")
    @classmethod
    def _bounded_utc(cls, ts: datetime | None) -> datetime | None:
        """Normalize to naive UTC and refuse timestamps that would skew attribution."""
        if ts is None:
            return None
        aware = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        if aware > now + MAX_CLOCK_SKEW:
            raise ValueError("timestamp is in the future")
        if aware < now - MAX_EVENT_AGE:
            raise ValueError("timestamp is older than 7 days")
        return aware.astimezone(UTC).replace(tzinfo=None)


class EventBatch(_Model):
    events: list[EventIn] = Field(min_length=1, max_length=MAX_BATCH)

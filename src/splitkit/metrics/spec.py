"""Metric definitions: validated from YAML before any SQL is generated."""

from __future__ import annotations

from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Names end up as bound parameters, never interpolated, but a strict pattern
# keeps garbage out of the database and makes metric files reviewable.
EVENT_PATTERN = r"^[a-z0-9_.:-]{1,64}$"
NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
MAX_WINDOW_DAYS = 365

Agg = Literal["any", "count", "sum"]


class EventAgg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event: str = Field(pattern=EVENT_PATTERN)
    agg: Agg = "count"


class MetricSpec(BaseModel):
    """proportion: share of users with >=1 event; mean: per-user count/sum;
    ratio: sum(numerator) / sum(denominator) across users (delta method)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=NAME_PATTERN)
    type: Literal["proportion", "mean", "ratio"]
    numerator: EventAgg
    denominator: EventAgg | None = None
    window_days: int | None = Field(default=None, ge=1, le=MAX_WINDOW_DAYS)
    description: str = ""

    @model_validator(mode="before")
    @classmethod
    def _expand_shorthand(cls, data: Any) -> Any:
        """Allow `event:` / `agg:` at top level for single-event metrics."""
        if not isinstance(data, dict) or "event" not in data:
            return data
        expanded = {k: v for k, v in data.items() if k not in ("event", "agg")}
        default_agg = "any" if data.get("type") == "proportion" else "count"
        expanded["numerator"] = {"event": data["event"], "agg": data.get("agg", default_agg)}
        return expanded

    @model_validator(mode="after")
    def _check_shape(self) -> MetricSpec:
        if self.type == "ratio" and self.denominator is None:
            raise ValueError("ratio metrics need a denominator")
        if self.type != "ratio" and self.denominator is not None:
            raise ValueError(f"{self.type} metrics cannot have a denominator")
        if self.type == "proportion" and self.numerator.agg != "any":
            raise ValueError("proportion metrics use agg 'any'")
        if self.type != "proportion" and self.numerator.agg == "any":
            raise ValueError("use type 'proportion' for has-any-event metrics")
        return self


def load_metrics(text: str) -> tuple[MetricSpec, ...]:
    data = yaml.safe_load(text)
    if not isinstance(data, dict) or not isinstance(data.get("metrics"), list):
        raise ValueError("metric file must be a mapping with a 'metrics' list")
    metrics = tuple(MetricSpec.model_validate(m) for m in data["metrics"])
    names = [m.name for m in metrics]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate metric names: {dupes}")
    return metrics

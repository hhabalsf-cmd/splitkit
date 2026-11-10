"""Compile a MetricSpec into SQL that returns one row of moments per variant.

Every user-supplied value (experiment key, event names, window) is a bound
parameter; only fixed SQL fragments chosen from whitelists are concatenated.

Output columns: variant, n, sum_x, sum_x2, sum_y, sum_y2, sum_xy
(y columns are NULL for non-ratio metrics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from splitkit.metrics.spec import EventAgg, MetricSpec

Dialect = Literal["duckdb", "postgres"]

# Per-user value of one event type, computed in the single events join below.
# Only these fixed fragments are concatenated; the event name is a bound parameter.
def _user_value(agg: EventAgg, param: str, dialect: Dialect) -> str:
    match = f"e.event_name = {_ph(param, dialect)}"
    if agg.agg == "any":
        return f"CAST(CASE WHEN COUNT(e.event_id) FILTER (WHERE {match}) > 0 THEN 1 ELSE 0 END AS DOUBLE PRECISION)"
    if agg.agg == "count":
        return f"CAST(COUNT(e.event_id) FILTER (WHERE {match}) AS DOUBLE PRECISION)"
    return f"CAST(COALESCE(SUM(e.value) FILTER (WHERE {match}), 0) AS DOUBLE PRECISION)"


@dataclass(frozen=True)
class CompiledQuery:
    sql: str
    params: dict[str, object] = field(default_factory=dict)


def _ph(name: str, dialect: Dialect) -> str:
    if dialect == "duckdb":
        return f"${name}"
    if dialect == "postgres":
        return f"%({name})s"
    raise ValueError(f"unsupported dialect: {dialect!r}")


def _clean_exposure_cte(dialect: Dialect, cutoff: bool = False) -> str:
    """First exposure per user; users seen in more than one variant are dropped.

    With a cutoff, only exposures before as_of exist: the readout as it
    would have looked at that moment.
    """
    exp = _ph("experiment_key", dialect)
    as_of = f"\n          AND assigned_at < {_ph('as_of', dialect)}" if cutoff else ""
    return f"""clean_exposure AS (
    SELECT user_id, variant, assigned_at
    FROM (
        SELECT user_id, variant, assigned_at,
               ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY assigned_at) AS rn,
               MIN(variant) OVER (PARTITION BY user_id) AS min_variant,
               MAX(variant) OVER (PARTITION BY user_id) AS max_variant
        FROM assignments
        WHERE experiment_key = {exp}{as_of}
    ) ranked
    WHERE rn = 1 AND min_variant = max_variant
)"""


def _event_join(names_sql: str, windowed: bool, cutoff: bool, dialect: Dialect) -> str:
    conditions = [
        "e.user_id = f.user_id",
        f"e.event_name IN ({names_sql})" if "," in names_sql else f"e.event_name = {names_sql}",
        "e.ts >= f.assigned_at",
    ]
    if windowed:
        conditions.append(f"e.ts < f.assigned_at + {_ph('window_days', dialect)} * INTERVAL '1 day'")
    if cutoff:
        conditions.append(f"e.ts < {_ph('as_of', dialect)}")
    return "\n       AND ".join(conditions)


def _validate_key(experiment_key: str) -> None:
    if not experiment_key or len(experiment_key) > 64:
        raise ValueError("experiment_key must be 1-64 characters")


def compile_metric(
    spec: MetricSpec,
    experiment_key: str,
    dialect: Dialect = "postgres",
    as_of: datetime | None = None,
) -> CompiledQuery:
    _validate_key(experiment_key)
    _ph("x", dialect)  # fail fast on unknown dialects
    windowed = spec.window_days is not None
    cutoff = as_of is not None
    params: dict[str, object] = {"experiment_key": experiment_key, "num_event": spec.numerator.event}
    if windowed:
        params["window_days"] = spec.window_days
    if cutoff:
        params["as_of"] = as_of

    # One LEFT JOIN from exposed users to their events, numerator and denominator
    # computed together with FILTER. Joining separately aggregated subqueries
    # instead lets a stale row estimate turn into a per-user re-aggregation.
    x_select = _user_value(spec.numerator, "num_event", dialect)
    names = _ph("num_event", dialect)
    if spec.denominator is not None:
        params["den_event"] = spec.denominator.event
        y_select = _user_value(spec.denominator, "den_event", dialect)
        names += ", " + _ph("den_event", dialect)
    else:
        y_select = "CAST(NULL AS DOUBLE PRECISION)"

    ctes = [
        _clean_exposure_cte(dialect, cutoff),
        f"""per_user AS (
    SELECT f.variant, {x_select} AS x, {y_select} AS y
    FROM clean_exposure f
    LEFT JOIN events e
        ON {_event_join(names, windowed, cutoff, dialect)}
    GROUP BY f.user_id, f.variant
)""",
    ]

    sql = "WITH " + ",\n".join(ctes) + """
SELECT variant,
       COUNT(*)    AS n,
       SUM(x)      AS sum_x,
       SUM(x * x)  AS sum_x2,
       SUM(y)      AS sum_y,
       SUM(y * y)  AS sum_y2,
       SUM(x * y)  AS sum_xy
FROM per_user
GROUP BY variant
ORDER BY variant"""
    return CompiledQuery(sql=sql, params=params)


def compile_assignment_counts(
    experiment_key: str, dialect: Dialect = "postgres", as_of: datetime | None = None
) -> CompiledQuery:
    """Users per variant after exclusions: the input to the SRM check."""
    _validate_key(experiment_key)
    sql = f"""WITH {_clean_exposure_cte(dialect, as_of is not None)}
SELECT variant, COUNT(*) AS n
FROM clean_exposure
GROUP BY variant
ORDER BY variant"""
    params: dict[str, object] = {"experiment_key": experiment_key}
    if as_of is not None:
        params["as_of"] = as_of
    return CompiledQuery(sql=sql, params=params)

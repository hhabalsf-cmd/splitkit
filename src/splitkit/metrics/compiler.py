"""Compile a MetricSpec into SQL that returns one row of moments per variant.

Every user-supplied value (experiment key, event names, window) is a bound
parameter; only fixed SQL fragments chosen from whitelists are concatenated.

Output columns: variant, n, sum_x, sum_x2, sum_y, sum_y2, sum_xy
(y columns are NULL for non-ratio metrics).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from splitkit.metrics.spec import EventAgg, MetricSpec

Dialect = Literal["duckdb", "postgres"]

_AGG_SQL = {
    "any": "CAST(1 AS DOUBLE PRECISION)",
    "count": "CAST(COUNT(*) AS DOUBLE PRECISION)",
    "sum": "CAST(SUM(COALESCE(e.value, 0)) AS DOUBLE PRECISION)",
}


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


def _clean_exposure_cte(dialect: Dialect) -> str:
    """First exposure per user; users seen in more than one variant are dropped."""
    exp = _ph("experiment_key", dialect)
    return f"""clean_exposure AS (
    SELECT user_id, variant, assigned_at
    FROM (
        SELECT user_id, variant, assigned_at,
               ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY assigned_at) AS rn,
               MIN(variant) OVER (PARTITION BY user_id) AS min_variant,
               MAX(variant) OVER (PARTITION BY user_id) AS max_variant
        FROM assignments
        WHERE experiment_key = {exp}
    ) ranked
    WHERE rn = 1 AND min_variant = max_variant
)"""


def _event_cte(alias: str, agg: EventAgg, param: str, windowed: bool, dialect: Dialect) -> str:
    window = (
        f"\n       AND e.ts < f.assigned_at + {_ph('window_days', dialect)} * INTERVAL '1 day'"
        if windowed
        else ""
    )
    return f"""{alias} AS (
    SELECT f.user_id, {_AGG_SQL[agg.agg]} AS value
    FROM clean_exposure f
    JOIN events e
        ON e.user_id = f.user_id
       AND e.event_name = {_ph(param, dialect)}
       AND e.ts >= f.assigned_at{window}
    GROUP BY f.user_id
)"""


def _validate_key(experiment_key: str) -> None:
    if not experiment_key or len(experiment_key) > 64:
        raise ValueError("experiment_key must be 1-64 characters")


def compile_metric(spec: MetricSpec, experiment_key: str, dialect: Dialect = "postgres") -> CompiledQuery:
    _validate_key(experiment_key)
    _ph("x", dialect)  # fail fast on unknown dialects
    windowed = spec.window_days is not None
    params: dict[str, object] = {"experiment_key": experiment_key, "num_event": spec.numerator.event}
    if windowed:
        params["window_days"] = spec.window_days

    ctes = [_clean_exposure_cte(dialect), _event_cte("num", spec.numerator, "num_event", windowed, dialect)]
    if spec.denominator is not None:
        params["den_event"] = spec.denominator.event
        ctes.append(_event_cte("den", spec.denominator, "den_event", windowed, dialect))
        y_select = "COALESCE(den.value, 0)"
        den_join = "\n    LEFT JOIN den ON den.user_id = f.user_id"
    else:
        y_select, den_join = "CAST(NULL AS DOUBLE PRECISION)", ""

    ctes.append(f"""per_user AS (
    SELECT f.variant, COALESCE(num.value, 0) AS x, {y_select} AS y
    FROM clean_exposure f
    LEFT JOIN num ON num.user_id = f.user_id{den_join}
)""")

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


def compile_assignment_counts(experiment_key: str, dialect: Dialect = "postgres") -> CompiledQuery:
    """Users per variant after exclusions: the input to the SRM check."""
    _validate_key(experiment_key)
    sql = f"""WITH {_clean_exposure_cte(dialect)}
SELECT variant, COUNT(*) AS n
FROM clean_exposure
GROUP BY variant
ORDER BY variant"""
    return CompiledQuery(sql=sql, params={"experiment_key": experiment_key})

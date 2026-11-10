"""Run an experiment readout: SRM gate -> per-metric SQL -> stats -> BH correction."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from splitkit.metrics.compiler import Dialect, compile_assignment_counts, compile_metric
from splitkit.metrics.spec import MetricSpec
from splitkit.stats.frequentist import TestResult, two_proportion_ztest
from splitkit.stats.multiple import benjamini_hochberg
from splitkit.stats.srm import DEFAULT_THRESHOLD, SrmResult, srm_check
from splitkit.stats.summary import (
    MomentSummary,
    RatioSummary,
    ratio_test_from_summary,
    welch_from_summary,
)

Fetcher = Callable[[str, dict[str, object]], list[tuple[Any, ...]]]


@dataclass(frozen=True)
class MetricAnalysis:
    metric: str
    type: str
    result: TestResult
    adjusted_p: float
    significant: bool
    sql: str


@dataclass(frozen=True)
class ExperimentAnalysis:
    experiment_key: str
    control: str
    treatment: str
    counts: dict[str, int]
    srm: SrmResult
    blocked: bool  # SRM failed: results are untrustworthy and never marked significant
    metrics: tuple[MetricAnalysis, ...]


def duckdb_fetcher(conn: Any) -> Fetcher:
    return lambda sql, params: conn.execute(sql, params).fetchall()


def postgres_fetcher(conn: Any) -> Fetcher:
    """psycopg 3 connection; queries must be compiled with dialect='postgres'."""
    def fetch(sql: str, params: dict[str, object]) -> list[tuple[Any, ...]]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    return fetch


def compare_metric(
    spec: MetricSpec, rows: dict[str, tuple], control: str, treatment: str, alpha: float = 0.05
) -> TestResult:
    """Run the test that fits the metric type on per-variant moment rows from the compiler."""
    a, b = rows[control], rows[treatment]  # (variant, n, sum_x, sum_x2, sum_y, sum_y2, sum_xy)
    if spec.type == "proportion":
        return two_proportion_ztest(int(a[2]), int(a[1]), int(b[2]), int(b[1]), alpha=alpha)
    if spec.type == "mean":
        return welch_from_summary(
            MomentSummary(int(a[1]), float(a[2]), float(a[3])),
            MomentSummary(int(b[1]), float(b[2]), float(b[3])),
            alpha=alpha,
        )
    to_ratio = lambda r: RatioSummary(int(r[1]), float(r[2]), float(r[4]), float(r[3]), float(r[5]), float(r[6]))  # noqa: E731
    return ratio_test_from_summary(to_ratio(a), to_ratio(b), alpha=alpha)


def analyze_experiment(
    fetch: Fetcher,
    experiment_key: str,
    metrics: Sequence[MetricSpec],
    control: str,
    treatment: str,
    weights: tuple[float, float] = (0.5, 0.5),
    alpha: float = 0.05,
    srm_threshold: float = DEFAULT_THRESHOLD,
    dialect: Dialect = "duckdb",
    as_of: datetime | None = None,
) -> ExperimentAnalysis:
    if len(weights) != 2:
        raise ValueError("weights must give (control, treatment) shares")

    q = compile_assignment_counts(experiment_key, dialect, as_of)
    counts = {str(v): int(n) for v, n in fetch(q.sql, q.params)}
    missing = [v for v in (control, treatment) if v not in counts]
    if missing:
        raise ValueError(f"variant(s) {missing} not found; have {sorted(counts)}")
    srm = srm_check([counts[control], counts[treatment]], list(weights), threshold=srm_threshold)

    compiled = [(spec, compile_metric(spec, experiment_key, dialect, as_of)) for spec in metrics]
    results = []
    for spec, cq in compiled:
        rows = {str(r[0]): r for r in fetch(cq.sql, cq.params)}
        results.append(compare_metric(spec, rows, control, treatment, alpha))

    bh = benjamini_hochberg([r.p_value for r in results], alpha=alpha)
    analyses = tuple(
        MetricAnalysis(
            metric=spec.name,
            type=spec.type,
            result=res,
            adjusted_p=adj,
            significant=rej and not srm.mismatch,
            sql=cq.sql,
        )
        for (spec, cq), res, adj, rej in zip(compiled, results, bh.adjusted, bh.rejected, strict=True)
    )
    return ExperimentAnalysis(
        experiment_key=experiment_key,
        control=control,
        treatment=treatment,
        counts=counts,
        srm=srm,
        blocked=srm.mismatch,
        metrics=analyses,
    )

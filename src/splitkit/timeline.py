"""Cumulative readout over time with always-valid p-values.

Replaying the metric query at increasing cutoffs shows how the estimate
evolved. The fixed-horizon p-value at each point is what a naive dashboard
shows (and what tempts peeking); the always-valid p-value is the running
minimum of the mSPRT p-value, which stays valid however often you look.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from splitkit.analysis import Fetcher, compare_metric
from splitkit.metrics.compiler import Dialect, compile_metric
from splitkit.metrics.spec import MetricSpec
from splitkit.stats.frequentist import TestResult
from splitkit.stats.sequential import msprt_from_estimate

# Mixture prior scale: plausible true lifts are up to ~10% of the control mean.
DEFAULT_RELATIVE_EFFECT = 0.10
MIN_TAU2 = 1e-12


@dataclass(frozen=True)
class TimelinePoint:
    as_of: datetime
    n_control: int
    n_treatment: int
    mean_a: float
    mean_b: float
    abs_lift: float
    ci_low: float
    ci_high: float
    p_value: float  # fixed-horizon: invalid if you act on it while peeking
    always_valid_p: float


def evenly_spaced(start: datetime, end: datetime, n: int) -> list[datetime]:
    """n cutoffs ending at `end`, the first one (end - start) / n after start."""
    if end <= start or n < 1:
        raise ValueError("need end > start and n >= 1")
    step = (end - start) / n
    return [start + step * (i + 1) for i in range(n)]


def experiment_timeline(
    fetch: Fetcher,
    experiment_key: str,
    metric: MetricSpec,
    control: str,
    treatment: str,
    points: Sequence[datetime],
    tau2: float | None = None,
    dialect: Dialect = "duckdb",
) -> tuple[TimelinePoint, ...]:
    """Points with fewer than 2 users in either arm are skipped.

    If tau2 is None it is (DEFAULT_RELATIVE_EFFECT x latest control mean)^2. The
    latest baseline is used because early cutoffs understate conversion metrics
    (recent users haven't had time to convert), which would shrink the prior
    and make the test needlessly conservative. tau2 is a prior hyperparameter
    and the control baseline carries no information about the treatment effect.
    """
    checkpoints: list[tuple[datetime, dict[str, tuple], TestResult]] = []
    for as_of in sorted(points):
        q = compile_metric(metric, experiment_key, dialect, as_of=as_of)
        rows = {str(r[0]): r for r in fetch(q.sql, q.params)}
        if control not in rows or treatment not in rows or min(rows[control][1], rows[treatment][1]) < 2:
            continue
        try:
            res = compare_metric(metric, rows, control, treatment)
        except ValueError:  # e.g. zero denominator so far
            continue
        checkpoints.append((as_of, rows, res))

    if not checkpoints:
        return ()
    if tau2 is None:
        tau2 = max((DEFAULT_RELATIVE_EFFECT * checkpoints[-1][2].mean_a) ** 2, MIN_TAU2)

    out: list[TimelinePoint] = []
    running = 1.0
    for as_of, rows, res in checkpoints:
        if res.std_error > 0:
            running = min(running, msprt_from_estimate(res.abs_lift, res.std_error**2, tau2))
        out.append(TimelinePoint(
            as_of=as_of,
            n_control=int(rows[control][1]),
            n_treatment=int(rows[treatment][1]),
            mean_a=res.mean_a,
            mean_b=res.mean_b,
            abs_lift=res.abs_lift,
            ci_low=res.ci_low,
            ci_high=res.ci_high,
            p_value=res.p_value,
            always_valid_p=running,
        ))
    return tuple(out)

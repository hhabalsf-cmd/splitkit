"""CUPED variance reduction (Deng et al., 2013) using a pre-experiment covariate."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from splitkit.stats.frequentist import TestResult, welch_ttest


@dataclass(frozen=True)
class CupedResult:
    result: TestResult
    theta: float
    variance_reduction: float  # fraction of metric variance removed, 0..1


def cuped_ttest(
    y_a: ArrayLike, x_a: ArrayLike, y_b: ArrayLike, x_b: ArrayLike, alpha: float = 0.05
) -> CupedResult:
    """Adjust y by theta * (x - mean(x)) with theta pooled across arms, then Welch test.

    The covariate must be measured before assignment, so it is independent of
    treatment and the adjusted estimate stays unbiased.
    """
    y_a, x_a, y_b, x_b = (np.asarray(v, dtype=float) for v in (y_a, x_a, y_b, x_b))
    if y_a.shape != x_a.shape or y_b.shape != x_b.shape:
        raise ValueError("metric and covariate arrays must have equal length per arm")

    y_all = np.concatenate([y_a, y_b])
    x_all = np.concatenate([x_a, x_b])
    x_var = x_all.var(ddof=1)
    if x_var == 0:
        raise ValueError("covariate has zero variance; CUPED cannot help")

    theta = float(np.cov(x_all, y_all, ddof=1)[0, 1] / x_var)
    x_mean = x_all.mean()
    adj_a = y_a - theta * (x_a - x_mean)
    adj_b = y_b - theta * (x_b - x_mean)

    y_var = y_all.var(ddof=1)
    adj_var = np.concatenate([adj_a, adj_b]).var(ddof=1)
    reduction = float(1 - adj_var / y_var) if y_var > 0 else 0.0

    return CupedResult(
        result=welch_ttest(adj_a, adj_b, alpha=alpha),
        theta=theta,
        variance_reduction=reduction,
    )

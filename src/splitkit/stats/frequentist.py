"""Fixed-horizon two-sample tests: two-proportion z-test and Welch's t-test."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats as sps


@dataclass(frozen=True)
class TestResult:
    """Comparison of treatment (B) against control (A). Lift is B - A."""

    __test__ = False  # keep pytest from collecting this as a test class

    mean_a: float
    mean_b: float
    abs_lift: float
    rel_lift: float
    std_error: float
    ci_low: float
    ci_high: float
    p_value: float
    alpha: float


def _relative(abs_lift: float, base: float) -> float:
    return abs_lift / base if base != 0 else float("nan")


def two_proportion_ztest(
    conv_a: int, n_a: int, conv_b: int, n_b: int, alpha: float = 0.05
) -> TestResult:
    """Pooled-SE z-test for the p-value, unpooled SE for the confidence interval."""
    for conv, n in ((conv_a, n_a), (conv_b, n_b)):
        if n <= 0 or conv < 0 or conv > n:
            raise ValueError(f"invalid counts: conversions={conv}, n={n}")

    p_a, p_b = conv_a / n_a, conv_b / n_b
    diff = p_b - p_a

    pooled = (conv_a + conv_b) / (n_a + n_b)
    se_pooled = np.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    p_value = 1.0 if se_pooled == 0 else 2 * sps.norm.sf(abs(diff) / se_pooled)

    se = float(np.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b))
    z = sps.norm.ppf(1 - alpha / 2)
    return TestResult(
        mean_a=p_a,
        mean_b=p_b,
        abs_lift=diff,
        rel_lift=_relative(diff, p_a),
        std_error=se,
        ci_low=diff - z * se,
        ci_high=diff + z * se,
        p_value=float(p_value),
        alpha=alpha,
    )


def welch_ttest(a: ArrayLike, b: ArrayLike, alpha: float = 0.05) -> TestResult:
    """Welch's unequal-variance t-test on per-user values."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.size < 2 or b.size < 2:
        raise ValueError("each arm needs at least 2 observations")

    va, vb = a.var(ddof=1) / a.size, b.var(ddof=1) / b.size
    se = float(np.sqrt(va + vb))
    diff = float(b.mean() - a.mean())
    df = (va + vb) ** 2 / (va**2 / (a.size - 1) + vb**2 / (b.size - 1))

    p_value = 1.0 if se == 0 else float(2 * sps.t.sf(abs(diff) / se, df))
    t_crit = sps.t.ppf(1 - alpha / 2, df)
    return TestResult(
        mean_a=float(a.mean()),
        mean_b=float(b.mean()),
        abs_lift=diff,
        rel_lift=_relative(diff, float(a.mean())),
        std_error=se,
        ci_low=diff - t_crit * se,
        ci_high=diff + t_crit * se,
        p_value=p_value,
        alpha=alpha,
    )

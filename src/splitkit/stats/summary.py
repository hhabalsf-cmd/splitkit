"""Tests computed from sufficient statistics instead of raw rows.

The SQL metric layer aggregates millions of per-user rows down to one row of
moments per variant (n, sum, sum of squares, ...). These functions run the
same tests as the raw-array versions using only those moments.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats as sps

from splitkit.stats.frequentist import TestResult, _relative


@dataclass(frozen=True)
class MomentSummary:
    n: int
    sum_x: float
    sum_x2: float

    def __post_init__(self) -> None:
        if self.n < 2:
            raise ValueError("need at least 2 users per variant")

    @property
    def mean(self) -> float:
        return self.sum_x / self.n

    @property
    def variance(self) -> float:
        """Sample variance (ddof=1), clamped at 0 against float round-off."""
        return max((self.sum_x2 - self.n * self.mean**2) / (self.n - 1), 0.0)


@dataclass(frozen=True)
class RatioSummary:
    """Per-user numerator x and denominator y moments for one variant."""

    n: int
    sum_x: float
    sum_y: float
    sum_x2: float
    sum_y2: float
    sum_xy: float

    def __post_init__(self) -> None:
        if self.n < 2:
            raise ValueError("need at least 2 users per variant")

    def ratio_and_variance(self) -> tuple[float, float]:
        n = self.n
        mu_x, mu_y = self.sum_x / n, self.sum_y / n
        if mu_y == 0:
            raise ValueError("denominator mean is zero")
        var_x = (self.sum_x2 - n * mu_x**2) / (n - 1)
        var_y = (self.sum_y2 - n * mu_y**2) / (n - 1)
        cov_xy = (self.sum_xy - n * mu_x * mu_y) / (n - 1)
        r = mu_x / mu_y
        var = (var_x - 2 * r * cov_xy + r**2 * var_y) / (n * mu_y**2)
        return r, max(var, 0.0)


def _normal_result(m_a: float, m_b: float, se: float, alpha: float) -> TestResult:
    diff = m_b - m_a
    z = sps.norm.ppf(1 - alpha / 2)
    p_value = 1.0 if se == 0 else float(2 * sps.norm.sf(abs(diff) / se))
    return TestResult(
        mean_a=m_a, mean_b=m_b, abs_lift=diff, rel_lift=_relative(diff, m_a),
        std_error=se, ci_low=diff - z * se, ci_high=diff + z * se,
        p_value=p_value, alpha=alpha,
    )


def welch_from_summary(a: MomentSummary, b: MomentSummary, alpha: float = 0.05) -> TestResult:
    va, vb = a.variance / a.n, b.variance / b.n
    se = float(np.sqrt(va + vb))
    diff = b.mean - a.mean
    denom = va**2 / (a.n - 1) + vb**2 / (b.n - 1)
    df = (va + vb) ** 2 / denom if denom > 0 else float(a.n + b.n - 2)
    p_value = 1.0 if se == 0 else float(2 * sps.t.sf(abs(diff) / se, df))
    t_crit = sps.t.ppf(1 - alpha / 2, df)
    return TestResult(
        mean_a=a.mean, mean_b=b.mean, abs_lift=diff, rel_lift=_relative(diff, a.mean),
        std_error=se, ci_low=diff - t_crit * se, ci_high=diff + t_crit * se,
        p_value=p_value, alpha=alpha,
    )


def ratio_test_from_summary(a: RatioSummary, b: RatioSummary, alpha: float = 0.05) -> TestResult:
    r_a, var_a = a.ratio_and_variance()
    r_b, var_b = b.ratio_and_variance()
    return _normal_result(r_a, r_b, float(np.sqrt(var_a + var_b)), alpha)

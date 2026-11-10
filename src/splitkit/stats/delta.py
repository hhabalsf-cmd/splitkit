"""Delta-method test for ratio metrics (e.g. revenue per session) randomized by user."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats as sps

from splitkit.stats.frequentist import TestResult, _relative


def _ratio_and_variance(num: np.ndarray, den: np.ndarray) -> tuple[float, float]:
    n = num.size
    mu_n, mu_d = num.mean(), den.mean()
    if mu_d == 0:
        raise ValueError("denominator mean is zero")
    ratio = mu_n / mu_d
    cov = np.cov(num, den, ddof=1)
    var = (cov[0, 0] - 2 * ratio * cov[0, 1] + ratio**2 * cov[1, 1]) / (n * mu_d**2)
    return float(ratio), float(max(var, 0.0))


def ratio_metric_test(
    num_a: ArrayLike, den_a: ArrayLike, num_b: ArrayLike, den_b: ArrayLike, alpha: float = 0.05
) -> TestResult:
    """Compare sum(num)/sum(den) between arms; per-user rows keep users as the unit."""
    arrays = [np.asarray(v, dtype=float) for v in (num_a, den_a, num_b, den_b)]
    num_a, den_a, num_b, den_b = arrays
    if num_a.shape != den_a.shape or num_b.shape != den_b.shape:
        raise ValueError("numerator and denominator lengths differ")
    if num_a.size < 2 or num_b.size < 2:
        raise ValueError("each arm needs at least 2 users")

    r_a, var_a = _ratio_and_variance(num_a, den_a)
    r_b, var_b = _ratio_and_variance(num_b, den_b)
    diff = r_b - r_a
    se = float(np.sqrt(var_a + var_b))
    z = sps.norm.ppf(1 - alpha / 2)
    p_value = 1.0 if se == 0 else float(2 * sps.norm.sf(abs(diff) / se))
    return TestResult(
        mean_a=r_a,
        mean_b=r_b,
        abs_lift=diff,
        rel_lift=_relative(diff, r_a),
        std_error=se,
        ci_low=diff - z * se,
        ci_high=diff + z * se,
        p_value=p_value,
        alpha=alpha,
    )

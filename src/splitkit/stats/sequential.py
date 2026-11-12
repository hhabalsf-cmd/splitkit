"""Always-valid p-values via the mixture SPRT (Johari et al., 2017).

Unlike a fixed-horizon test, these p-values can be checked after every new
observation without inflating the false-positive rate.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

MIN_OBSERVATIONS = 10  # variance estimate is too noisy before this


def msprt_pvalue(diff: float, var_diff: float, n: int, tau2: float) -> float:
    """1 / likelihood ratio of a normal mixture (prior N(0, tau2)) vs. the null.

    diff: running mean of per-observation differences.
    var_diff: variance of a single difference observation.
    """
    if var_diff <= 0 or tau2 <= 0:
        raise ValueError("variances must be positive")
    if n < 1:
        raise ValueError("n must be at least 1")
    denom = var_diff + n * tau2
    log_lr = 0.5 * np.log(var_diff / denom) + (n**2 * tau2 * diff**2) / (2 * var_diff * denom)
    return float(min(1.0, np.exp(-log_lr)))


def msprt_from_estimate(estimate: float, variance: float, tau2: float) -> float:
    """Same mixture test, stated for any asymptotically normal estimate (e.g. a lift).

    With V = variance of the estimate this equals msprt_pvalue(diff, V * n, n, tau2),
    so it applies to proportions, Welch means and delta-method ratios alike.
    """
    if variance <= 0 or tau2 <= 0:
        raise ValueError("variances must be positive")
    denom = variance + tau2
    log_lr = 0.5 * np.log(variance / denom) + (tau2 * estimate**2) / (2 * variance * denom)
    return float(min(1.0, np.exp(-log_lr)))


def sequential_pvalues(
    diffs: ArrayLike, tau2: float, var_diff: float | None = None
) -> list[float]:
    """Running always-valid p-values for a stream of paired differences (B - A).

    If var_diff is None, the variance is estimated from the data seen so far.
    The sequence is monotone non-increasing by construction.
    """
    d = np.asarray(diffs, dtype=float)
    n_idx = np.arange(1, d.size + 1)
    means = np.cumsum(d) / n_idx
    if var_diff is None:
        sq = np.cumsum(d**2)
        variances = np.where(n_idx > 1, (sq - n_idx * means**2) / np.maximum(n_idx - 1, 1), 0.0)
    else:
        variances = np.full(d.size, float(var_diff))

    valid = (n_idx >= MIN_OBSERVATIONS) & (variances > 0)
    safe_var = np.where(valid, variances, 1.0)
    denom = safe_var + n_idx * tau2
    log_lr = 0.5 * np.log(safe_var / denom) + (n_idx**2 * tau2 * means**2) / (2 * safe_var * denom)
    pvals = np.where(valid, np.minimum(1.0, np.exp(-log_lr)), 1.0)
    return np.minimum.accumulate(pvals).tolist()

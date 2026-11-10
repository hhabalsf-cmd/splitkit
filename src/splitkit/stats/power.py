"""Sample-size and minimum-detectable-effect planning for conversion metrics."""

from __future__ import annotations

import math

from scipy import optimize
from scipy import stats as sps


def _validate(baseline: float, alpha: float, power: float) -> None:
    if not 0 < baseline < 1:
        raise ValueError("baseline must be in (0, 1)")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError("alpha and power must be in (0, 1)")


def _n_continuous(baseline: float, mde_abs: float, alpha: float, power: float) -> float:
    p2 = baseline + mde_abs
    if not 0 < p2 < 1:
        raise ValueError("baseline + mde must stay in (0, 1)")
    z = sps.norm.ppf(1 - alpha / 2) + sps.norm.ppf(power)
    variance = baseline * (1 - baseline) + p2 * (1 - p2)
    return z**2 * variance / mde_abs**2


def required_sample_size_proportion(
    baseline: float, mde_abs: float, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Users needed *per arm* to detect an absolute lift of mde_abs (two-sided)."""
    _validate(baseline, alpha, power)
    if mde_abs == 0:
        raise ValueError("mde must be non-zero")
    return math.ceil(_n_continuous(baseline, mde_abs, alpha, power))


def minimum_detectable_effect(
    baseline: float, n_per_arm: int, alpha: float = 0.05, power: float = 0.8
) -> float:
    """Smallest positive absolute lift detectable with n_per_arm users per arm."""
    _validate(baseline, alpha, power)
    if n_per_arm < 2:
        raise ValueError("n_per_arm must be at least 2")
    upper = (1 - baseline) - 1e-9
    return float(
        optimize.brentq(
            lambda m: _n_continuous(baseline, m, alpha, power) - n_per_arm, 1e-9, upper
        )
    )

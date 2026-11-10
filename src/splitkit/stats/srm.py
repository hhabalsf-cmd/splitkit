"""Sample Ratio Mismatch check: are assignment counts consistent with the planned split?"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy import stats as sps

DEFAULT_THRESHOLD = 0.001  # conventional; SRM checks run on every experiment


@dataclass(frozen=True)
class SrmResult:
    p_value: float
    mismatch: bool
    expected: tuple[float, ...]


def srm_check(
    observed: Sequence[int],
    expected_weights: Sequence[float],
    threshold: float = DEFAULT_THRESHOLD,
) -> SrmResult:
    obs = np.asarray(observed, dtype=float)
    weights = np.asarray(expected_weights, dtype=float)
    if obs.size < 2 or obs.size != weights.size:
        raise ValueError("need matching observed counts and weights for 2+ variants")
    if not np.isclose(weights.sum(), 1.0) or (weights <= 0).any():
        raise ValueError("weights must be positive and sum to 1")
    if (obs < 0).any():
        raise ValueError("counts must be non-negative")

    expected = weights * obs.sum()
    p_value = float(sps.chisquare(obs, expected).pvalue)
    return SrmResult(
        p_value=p_value,
        mismatch=p_value < threshold,
        expected=tuple(float(e) for e in expected),
    )

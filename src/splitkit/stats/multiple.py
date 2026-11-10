"""Benjamini-Hochberg false discovery rate control across multiple metrics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MultipleTestResult:
    adjusted: tuple[float, ...]
    rejected: tuple[bool, ...]


def benjamini_hochberg(p_values: Sequence[float], alpha: float = 0.05) -> MultipleTestResult:
    p = np.asarray(p_values, dtype=float)
    if ((p < 0) | (p > 1)).any():
        raise ValueError("p-values must be in [0, 1]")
    m = p.size
    order = np.argsort(p)
    scaled = p[order] * m / np.arange(1, m + 1)
    monotone = np.minimum.accumulate(scaled[::-1])[::-1]
    adjusted_sorted = np.minimum(monotone, 1.0)

    adjusted = np.empty(m)
    adjusted[order] = adjusted_sorted
    return MultipleTestResult(
        adjusted=tuple(float(a) for a in adjusted),
        rejected=tuple(bool(a <= alpha) for a in adjusted),
    )

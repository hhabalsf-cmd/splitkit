"""Monte-Carlo validation of the stats engine against known ground truth.

Each simulated experiment draws Bernoulli conversions for two arms with a known
true lift, then records whether each analysis method declared significance:
  * fixed-horizon z-test at the planned sample size (the textbook test)
  * the same z-test checked at `peeks` interim looks (what dashboards tempt you to do)
  * mSPRT always-valid p-values checked after every user pair
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from splitkit.stats.frequentist import two_proportion_ztest
from splitkit.stats.power import required_sample_size_proportion
from splitkit.stats.sequential import sequential_pvalues


@dataclass(frozen=True)
class SimConfig:
    n_sims: int = 1000
    n_per_arm: int = 5000
    baseline: float = 0.10
    true_lift: float = 0.0  # absolute
    alpha: float = 0.05
    peeks: int = 10
    tau2: float = 4e-4  # mixture prior variance ~ (expected effect size)^2
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n_sims < 1 or self.n_per_arm < 10 or self.peeks < 1:
            raise ValueError("n_sims >= 1, n_per_arm >= 10 and peeks >= 1 required")
        if not 0 < self.baseline < 1 or not 0 < self.baseline + self.true_lift < 1:
            raise ValueError("baseline and baseline + true_lift must be in (0, 1)")


@dataclass(frozen=True)
class SimReport:
    config: SimConfig
    fixed_horizon_reject_rate: float
    naive_peeking_reject_rate: float
    sequential_reject_rate: float


def _peek_rejects(a: np.ndarray, b: np.ndarray, peeks: int, alpha: float) -> bool:
    n = a.size
    checkpoints = np.linspace(n / peeks, n, peeks).astype(int)
    return any(
        two_proportion_ztest(int(a[:k].sum()), k, int(b[:k].sum()), k).p_value < alpha
        for k in checkpoints
    )


def run_simulation(config: SimConfig) -> SimReport:
    rng = np.random.default_rng(config.seed)
    n = config.n_per_arm
    fixed = peeking = sequential = 0

    for _ in range(config.n_sims):
        a = (rng.random(n) < config.baseline).astype(float)
        b = (rng.random(n) < config.baseline + config.true_lift).astype(float)

        final = two_proportion_ztest(int(a.sum()), n, int(b.sum()), n)
        fixed += final.p_value < config.alpha
        peeking += _peek_rejects(a, b, config.peeks, config.alpha)
        sequential += sequential_pvalues(b - a, tau2=config.tau2)[-1] < config.alpha

    return SimReport(
        config=config,
        fixed_horizon_reject_rate=fixed / config.n_sims,
        naive_peeking_reject_rate=peeking / config.n_sims,
        sequential_reject_rate=sequential / config.n_sims,
    )


# --- detection delay -------------------------------------------------------------------
#
# The price of always-valid p-values: how much more data mSPRT needs to catch a real
# effect than a fixed-horizon test planned for 80% power.


@dataclass(frozen=True)
class DetectionConfig:
    n_sims: int = 1000
    baseline: float = 0.10
    true_lift: float = 0.015  # absolute; the effect actually present in the data
    mde: float | None = None  # effect the fixed test is planned for; defaults to true_lift
    alpha: float = 0.05
    power: float = 0.8
    tau2: float = 4e-4
    horizon_multiplier: float = 4.0  # stream length, in multiples of the fixed-horizon n
    seed: int = 0

    def __post_init__(self) -> None:
        if self.n_sims < 1:
            raise ValueError("n_sims must be at least 1")
        if not 0 < self.alpha < 1 or not 0 < self.power < 1:
            raise ValueError("alpha and power must be in (0, 1)")
        if self.horizon_multiplier < 1:
            raise ValueError("horizon_multiplier must be at least 1")
        if self.planned_effect == 0:
            raise ValueError("need a non-zero true_lift or mde to plan the fixed test")
        if not 0 < self.baseline < 1 or not 0 < self.baseline + self.true_lift < 1:
            raise ValueError("baseline and baseline + true_lift must be in (0, 1)")

    @property
    def planned_effect(self) -> float:
        return self.mde if self.mde is not None else self.true_lift


@dataclass(frozen=True)
class DetectionReport:
    config: DetectionConfig
    fixed_n_per_arm: int  # fixed-horizon n per arm for the target power
    horizon_n_per_arm: int
    detected_rate: float  # share of sims where mSPRT crossed alpha within the horizon
    msprt_power_at_fixed_n: float  # share detected by the time the fixed test would read out
    median_stop_n: int | None  # median n per arm at detection (None if < half detected)
    msprt_n_for_power: int | None  # n per arm at which mSPRT reaches the target power
    n_ratio: float | None  # msprt_n_for_power / fixed_n_per_arm


def _first_crossing(pvalues: list[float], alpha: float) -> int | None:
    """1-based n at which the always-valid p-value first drops below alpha."""
    hits = np.flatnonzero(np.asarray(pvalues) < alpha)
    return int(hits[0]) + 1 if hits.size else None


def _quantile_stop(stops: np.ndarray, q: float) -> int | None:
    """q-quantile of stopping n, counting undetected sims (inf) as never stopping."""
    value = float(np.quantile(stops, q, method="higher"))
    return int(value) if np.isfinite(value) else None


def run_detection_simulation(config: DetectionConfig) -> DetectionReport:
    rng = np.random.default_rng(config.seed)
    fixed_n = required_sample_size_proportion(
        config.baseline, config.planned_effect, config.alpha, config.power
    )
    horizon = int(np.ceil(fixed_n * config.horizon_multiplier))

    stops = np.full(config.n_sims, np.inf)
    for i in range(config.n_sims):
        a = (rng.random(horizon) < config.baseline).astype(float)
        b = (rng.random(horizon) < config.baseline + config.true_lift).astype(float)
        stop = _first_crossing(sequential_pvalues(b - a, tau2=config.tau2), config.alpha)
        if stop is not None:
            stops[i] = stop

    n_for_power = _quantile_stop(stops, config.power)
    return DetectionReport(
        config=config,
        fixed_n_per_arm=fixed_n,
        horizon_n_per_arm=horizon,
        detected_rate=float(np.isfinite(stops).mean()),
        msprt_power_at_fixed_n=float((stops <= fixed_n).mean()),
        median_stop_n=_quantile_stop(stops, 0.5),
        msprt_n_for_power=n_for_power,
        n_ratio=None if n_for_power is None else n_for_power / fixed_n,
    )

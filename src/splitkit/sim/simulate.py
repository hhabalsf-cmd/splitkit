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

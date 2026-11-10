"""Run the validation simulations and print a summary table (CLI output)."""

import sys
import time

from splitkit.sim.simulate import SimConfig, run_simulation

SCENARIOS = {
    "A/A (no effect)": SimConfig(n_sims=1000, n_per_arm=5000, true_lift=0.0, peeks=10, seed=10),
    "A/B (+1.5pt lift)": SimConfig(n_sims=1000, n_per_arm=5000, true_lift=0.015, peeks=10, seed=11),
}


def main() -> int:
    header = f"{'scenario':<20}{'fixed':>8}{'peek x10':>10}{'mSPRT':>8}"
    sys.stdout.write(header + "\n" + "-" * len(header) + "\n")
    for name, cfg in SCENARIOS.items():
        start = time.perf_counter()
        r = run_simulation(cfg)
        sys.stdout.write(
            f"{name:<20}{r.fixed_horizon_reject_rate:>8.3f}{r.naive_peeking_reject_rate:>10.3f}"
            f"{r.sequential_reject_rate:>8.3f}   ({time.perf_counter() - start:.1f}s)\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

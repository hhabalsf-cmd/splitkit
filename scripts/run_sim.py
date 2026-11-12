"""Run the validation simulations and print a summary table (CLI output)."""

import sys
import time

from splitkit.sim.simulate import DetectionConfig, SimConfig, run_detection_simulation, run_simulation

SCENARIOS = {
    "A/A (no effect)": SimConfig(n_sims=1000, n_per_arm=5000, true_lift=0.0, peeks=10, seed=10),
    "A/B (+1.5pt lift)": SimConfig(n_sims=1000, n_per_arm=5000, true_lift=0.015, peeks=10, seed=11),
}

DETECTION = DetectionConfig(n_sims=1000, baseline=0.10, true_lift=0.015, power=0.8, seed=12)


def _fmt(n: int | None) -> str:
    return f"{n:,}" if n is not None else "n/a"


def detection_summary() -> None:
    start = time.perf_counter()
    r = run_detection_simulation(DETECTION)
    ratio = f"{r.n_ratio:.2f}x" if r.n_ratio is not None else "not reached"
    sys.stdout.write(
        f"\nDetection delay, +{DETECTION.true_lift * 100:.1f}pt on {DETECTION.baseline:.0%} "
        f"({DETECTION.n_sims} sims, horizon {r.horizon_n_per_arm:,}/arm)\n"
        f"  fixed-horizon n/arm for {DETECTION.power:.0%} power : {r.fixed_n_per_arm:,}\n"
        f"  mSPRT power at that n               : {r.msprt_power_at_fixed_n:.1%}\n"
        f"  mSPRT n/arm for {DETECTION.power:.0%} power         : {_fmt(r.msprt_n_for_power)} ({ratio})\n"
        f"  mSPRT median stopping n/arm         : {_fmt(r.median_stop_n)}\n"
        f"  detected within horizon             : {r.detected_rate:.1%}"
        f"   ({time.perf_counter() - start:.1f}s)\n"
    )


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
    detection_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

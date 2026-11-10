import pytest

from splitkit.sim.simulate import SimConfig, run_simulation


def test_aa_fixed_horizon_fpr_near_alpha():
    report = run_simulation(SimConfig(n_sims=300, n_per_arm=2000, true_lift=0.0, seed=1))
    assert report.fixed_horizon_reject_rate == pytest.approx(0.05, abs=0.03)


def test_naive_peeking_inflates_fpr_and_sequential_does_not():
    report = run_simulation(SimConfig(n_sims=300, n_per_arm=2000, true_lift=0.0, peeks=20, seed=2))
    assert report.naive_peeking_reject_rate > 0.10
    assert report.sequential_reject_rate <= 0.07


def test_ab_power_increases_with_effect():
    small = run_simulation(SimConfig(n_sims=200, n_per_arm=2000, true_lift=0.005, seed=3))
    large = run_simulation(SimConfig(n_sims=200, n_per_arm=2000, true_lift=0.03, seed=3))
    assert large.fixed_horizon_reject_rate > small.fixed_horizon_reject_rate
    assert large.fixed_horizon_reject_rate > 0.8


def test_config_validation():
    with pytest.raises(ValueError):
        SimConfig(n_sims=0)
    with pytest.raises(ValueError):
        SimConfig(baseline=0.95, true_lift=0.1)

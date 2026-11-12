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


# --- detection delay: how much later mSPRT detects a real effect than a fixed-horizon test


from splitkit.sim.simulate import DetectionConfig, run_detection_simulation  # noqa: E402
from splitkit.stats.power import required_sample_size_proportion  # noqa: E402


def test_detection_fixed_n_comes_from_power_calculation():
    cfg = DetectionConfig(n_sims=20, baseline=0.10, true_lift=0.03, seed=4)
    report = run_detection_simulation(cfg)
    assert report.fixed_n_per_arm == required_sample_size_proportion(0.10, 0.03, 0.05, 0.8)


def test_detection_is_deterministic_for_a_seed():
    cfg = DetectionConfig(n_sims=30, baseline=0.10, true_lift=0.03, seed=5)
    assert run_detection_simulation(cfg) == run_detection_simulation(cfg)


def test_strong_effect_detected_in_nearly_every_sim():
    report = run_detection_simulation(
        DetectionConfig(n_sims=100, baseline=0.10, true_lift=0.05, seed=6)
    )
    assert report.detected_rate >= 0.95
    assert report.median_stop_n is not None


def test_msprt_needs_more_data_than_fixed_horizon_for_same_power():
    report = run_detection_simulation(
        DetectionConfig(n_sims=200, baseline=0.10, true_lift=0.03, seed=7)
    )
    assert report.msprt_n_for_power is not None
    assert report.msprt_n_for_power >= report.fixed_n_per_arm
    assert report.n_ratio == pytest.approx(report.msprt_n_for_power / report.fixed_n_per_arm)
    # at the fixed-horizon sample size mSPRT has less power than the fixed test's 80%
    assert report.msprt_power_at_fixed_n < 0.8


def test_no_effect_rejections_stay_below_alpha():
    report = run_detection_simulation(
        DetectionConfig(n_sims=200, baseline=0.10, true_lift=0.0, mde=0.03, seed=8)
    )
    assert report.detected_rate <= 0.07


def test_power_target_not_reached_within_horizon_gives_none():
    report = run_detection_simulation(
        DetectionConfig(n_sims=20, baseline=0.10, true_lift=0.0, mde=0.03, horizon_multiplier=1.0, seed=9)
    )
    assert report.msprt_n_for_power is None
    assert report.n_ratio is None


def test_detection_config_validation():
    with pytest.raises(ValueError):
        DetectionConfig(n_sims=0)
    with pytest.raises(ValueError):
        DetectionConfig(true_lift=0.0)  # no mde to plan the fixed test against
    with pytest.raises(ValueError):
        DetectionConfig(horizon_multiplier=0.5)
    with pytest.raises(ValueError):
        DetectionConfig(power=1.2)

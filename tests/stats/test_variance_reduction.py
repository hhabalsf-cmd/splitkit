import numpy as np
import pytest

from splitkit.stats.cuped import cuped_ttest
from splitkit.stats.delta import ratio_metric_test
from splitkit.stats.frequentist import welch_ttest


def _correlated_arms(rng, n, effect):
    pre_a = rng.normal(100, 20, n)
    pre_b = rng.normal(100, 20, n)
    post_a = 0.8 * pre_a + rng.normal(20, 8, n)
    post_b = 0.8 * pre_b + rng.normal(20 + effect, 8, n)
    return post_a, pre_a, post_b, pre_b


class TestCuped:
    def test_shrinks_confidence_interval(self):
        rng = np.random.default_rng(42)
        ya, xa, yb, xb = _correlated_arms(rng, 2000, effect=1.0)
        plain = welch_ttest(ya, yb)
        cuped = cuped_ttest(ya, xa, yb, xb)
        plain_w = plain.ci_high - plain.ci_low
        cuped_w = cuped.result.ci_high - cuped.result.ci_low
        assert cuped_w < 0.6 * plain_w
        assert cuped.variance_reduction > 0.5

    def test_estimate_is_unbiased(self):
        rng = np.random.default_rng(7)
        lifts = [cuped_ttest(*_correlated_arms(rng, 500, effect=2.0)).result.abs_lift for _ in range(200)]
        assert np.mean(lifts) == pytest.approx(2.0, abs=0.15)

    def test_theta_is_pooled_regression_slope(self):
        rng = np.random.default_rng(3)
        ya, xa, yb, xb = _correlated_arms(rng, 5000, effect=0.0)
        assert cuped_ttest(ya, xa, yb, xb).theta == pytest.approx(0.8, abs=0.05)

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            cuped_ttest(np.ones(5), np.ones(4), np.ones(5), np.ones(5))


class TestDeltaMethod:
    def test_constant_denominator_reduces_to_mean_test(self):
        rng = np.random.default_rng(0)
        num_a, num_b = rng.normal(10, 3, 1000), rng.normal(10.5, 3, 1000)
        den = np.ones(1000)
        res = ratio_metric_test(num_a, den, num_b, den)
        ref = welch_ttest(num_a, num_b)
        assert res.abs_lift == pytest.approx(ref.abs_lift)
        # Delta uses a normal reference, Welch a t reference: SEs agree, far tails differ slightly
        assert res.std_error == pytest.approx(ref.std_error, rel=1e-3)

    def test_coverage_close_to_nominal(self):
        rng = np.random.default_rng(11)
        covered = 0
        trials = 300
        for _ in range(trials):
            sessions_a = rng.poisson(5, 800) + 1
            sessions_b = rng.poisson(5, 800) + 1
            rev_a = rng.gamma(2.0, 1.0, 800) * sessions_a
            rev_b = rng.gamma(2.0, 1.0, 800) * sessions_b
            res = ratio_metric_test(rev_a, sessions_a, rev_b, sessions_b)
            covered += res.ci_low <= 0.0 <= res.ci_high
        assert 0.92 <= covered / trials <= 0.98

    def test_zero_denominator_raises(self):
        with pytest.raises(ValueError):
            ratio_metric_test(np.ones(3), np.zeros(3), np.ones(3), np.ones(3))

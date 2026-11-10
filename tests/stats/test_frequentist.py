import numpy as np
import pytest
from scipy import stats as sps
from statsmodels.stats.proportion import proportions_ztest

from splitkit.stats.frequentist import two_proportion_ztest, welch_ttest


class TestTwoProportionZTest:
    def test_matches_statsmodels_pvalue(self):
        res = two_proportion_ztest(conv_a=200, n_a=2000, conv_b=240, n_b=2000)
        _, p_ref = proportions_ztest([240, 200], [2000, 2000])
        assert res.p_value == pytest.approx(p_ref, rel=1e-6)

    def test_absolute_lift_and_relative_lift(self):
        res = two_proportion_ztest(conv_a=100, n_a=1000, conv_b=120, n_b=1000)
        assert res.mean_a == pytest.approx(0.10)
        assert res.mean_b == pytest.approx(0.12)
        assert res.abs_lift == pytest.approx(0.02)
        assert res.rel_lift == pytest.approx(0.20)

    def test_ci_uses_unpooled_standard_error(self):
        res = two_proportion_ztest(conv_a=100, n_a=1000, conv_b=120, n_b=1000)
        se = np.sqrt(0.1 * 0.9 / 1000 + 0.12 * 0.88 / 1000)
        z = sps.norm.ppf(0.975)
        assert res.ci_low == pytest.approx(0.02 - z * se)
        assert res.ci_high == pytest.approx(0.02 + z * se)

    def test_rejects_invalid_counts(self):
        with pytest.raises(ValueError):
            two_proportion_ztest(conv_a=11, n_a=10, conv_b=1, n_b=10)
        with pytest.raises(ValueError):
            two_proportion_ztest(conv_a=0, n_a=0, conv_b=1, n_b=10)

    def test_result_is_immutable(self):
        res = two_proportion_ztest(conv_a=1, n_a=10, conv_b=2, n_b=10)
        with pytest.raises(AttributeError):
            res.p_value = 0.0


class TestWelchTTest:
    def test_matches_scipy(self):
        rng = np.random.default_rng(0)
        a = rng.normal(10, 2, 500)
        b = rng.normal(10.3, 3, 700)
        res = welch_ttest(a, b)
        ref = sps.ttest_ind(b, a, equal_var=False)
        assert res.p_value == pytest.approx(ref.pvalue, rel=1e-6)
        assert res.abs_lift == pytest.approx(b.mean() - a.mean())

    def test_ci_matches_scipy_confidence_interval(self):
        rng = np.random.default_rng(1)
        a = rng.normal(5, 1, 300)
        b = rng.normal(5.2, 1.5, 300)
        res = welch_ttest(a, b, alpha=0.1)
        ci = sps.ttest_ind(b, a, equal_var=False).confidence_interval(0.9)
        assert res.ci_low == pytest.approx(ci.low, rel=1e-6)
        assert res.ci_high == pytest.approx(ci.high, rel=1e-6)

    def test_requires_two_observations_per_arm(self):
        with pytest.raises(ValueError):
            welch_ttest(np.array([1.0]), np.array([1.0, 2.0]))

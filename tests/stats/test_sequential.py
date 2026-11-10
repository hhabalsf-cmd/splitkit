import numpy as np
import pytest

from splitkit.stats.sequential import msprt_pvalue, sequential_pvalues


class TestMsprt:
    def test_pvalue_bounded_in_unit_interval(self):
        p = msprt_pvalue(diff=0.5, var_diff=1.0, n=100, tau2=1.0)
        assert 0.0 < p <= 1.0

    def test_larger_effect_gives_smaller_pvalue(self):
        small = msprt_pvalue(diff=0.1, var_diff=1.0, n=1000, tau2=0.01)
        large = msprt_pvalue(diff=0.3, var_diff=1.0, n=1000, tau2=0.01)
        assert large < small

    def test_sequence_is_nonincreasing(self):
        rng = np.random.default_rng(0)
        diffs = rng.normal(0.0, 1.0, 2000)
        ps = sequential_pvalues(diffs, tau2=0.01)
        assert all(b <= a + 1e-12 for a, b in zip(ps, ps[1:], strict=False))

    def test_aa_false_positive_rate_controlled_under_continuous_peeking(self):
        rng = np.random.default_rng(123)
        sims, n, alpha = 400, 1500, 0.05
        false_pos = 0
        for _ in range(sims):
            diffs = rng.normal(0.0, 1.0, n)
            false_pos += min(sequential_pvalues(diffs, tau2=0.01)) < alpha
        assert false_pos / sims <= alpha + 0.02

    def test_detects_true_effect(self):
        rng = np.random.default_rng(5)
        diffs = rng.normal(0.2, 1.0, 3000)
        assert sequential_pvalues(diffs, tau2=0.01)[-1] < 0.01

    def test_invalid_args(self):
        with pytest.raises(ValueError):
            msprt_pvalue(diff=0.1, var_diff=-1.0, n=10, tau2=1.0)
        with pytest.raises(ValueError):
            msprt_pvalue(diff=0.1, var_diff=1.0, n=0, tau2=1.0)

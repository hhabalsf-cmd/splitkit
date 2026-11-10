import numpy as np
import pytest
from scipy import stats as sps
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize

from splitkit.stats.multiple import benjamini_hochberg
from splitkit.stats.power import required_sample_size_proportion, minimum_detectable_effect
from splitkit.stats.srm import srm_check


class TestSRM:
    def test_matches_scipy_chisquare(self):
        res = srm_check(observed=[5000, 5200], expected_weights=[0.5, 0.5])
        ref = sps.chisquare([5000, 5200], [5100, 5100])
        assert res.p_value == pytest.approx(ref.pvalue)

    def test_flags_mismatch_below_threshold(self):
        assert srm_check([5000, 5600], [0.5, 0.5]).mismatch is True
        assert srm_check([5000, 5010], [0.5, 0.5]).mismatch is False

    def test_supports_unequal_weights(self):
        res = srm_check([9000, 1000], [0.9, 0.1])
        assert res.mismatch is False

    def test_validates_inputs(self):
        with pytest.raises(ValueError):
            srm_check([10, 10], [0.5, 0.4])
        with pytest.raises(ValueError):
            srm_check([10], [1.0])


class TestBenjaminiHochberg:
    def test_matches_statsmodels(self):
        p = [0.001, 0.01, 0.03, 0.04, 0.2, 0.5]
        res = benjamini_hochberg(p, alpha=0.05)
        rej_ref, adj_ref, _, _ = multipletests(p, alpha=0.05, method="fdr_bh")
        assert res.rejected == tuple(bool(x) for x in rej_ref)
        np.testing.assert_allclose(res.adjusted, adj_ref)

    def test_preserves_input_order(self):
        res = benjamini_hochberg([0.5, 0.001], alpha=0.05)
        assert res.rejected == (False, True)

    def test_rejects_out_of_range(self):
        with pytest.raises(ValueError):
            benjamini_hochberg([0.1, 1.2])


class TestPower:
    def test_sample_size_matches_statsmodels(self):
        n = required_sample_size_proportion(baseline=0.10, mde_abs=0.01, alpha=0.05, power=0.8)
        es = proportion_effectsize(0.11, 0.10)
        ref = NormalIndPower().solve_power(effect_size=es, alpha=0.05, power=0.8, ratio=1.0)
        # Normal-approx (unpooled) and arcsine formulas agree within ~1%
        assert n == pytest.approx(ref, rel=0.02)
        assert isinstance(n, int)

    def test_mde_inverts_sample_size(self):
        n = required_sample_size_proportion(0.2, 0.02)
        mde = minimum_detectable_effect(0.2, n)
        assert mde == pytest.approx(0.02, rel=0.02)

    def test_validates_baseline(self):
        with pytest.raises(ValueError):
            required_sample_size_proportion(1.2, 0.01)

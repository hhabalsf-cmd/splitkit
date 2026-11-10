import numpy as np
import pytest

from splitkit.stats.delta import ratio_metric_test
from splitkit.stats.frequentist import welch_ttest
from splitkit.stats.summary import (
    MomentSummary,
    RatioSummary,
    ratio_test_from_summary,
    welch_from_summary,
)


def _moments(x: np.ndarray) -> MomentSummary:
    return MomentSummary(n=x.size, sum_x=float(x.sum()), sum_x2=float((x**2).sum()))


def test_moment_summary_mean_and_variance():
    x = np.array([1.0, 2.0, 3.0, 6.0])
    s = _moments(x)
    assert s.mean == pytest.approx(3.0)
    assert s.variance == pytest.approx(x.var(ddof=1))


def test_welch_from_summary_matches_raw_arrays():
    rng = np.random.default_rng(0)
    a, b = rng.exponential(3, 800), rng.exponential(3.4, 900)
    from_raw = welch_ttest(a, b)
    from_sum = welch_from_summary(_moments(a), _moments(b))
    assert from_sum.p_value == pytest.approx(from_raw.p_value, rel=1e-9)
    assert from_sum.ci_low == pytest.approx(from_raw.ci_low, rel=1e-9)


def test_ratio_from_summary_matches_raw_arrays():
    rng = np.random.default_rng(1)
    da, db = rng.poisson(4, 500) + 1.0, rng.poisson(4, 500) + 1.0
    na, nb = rng.gamma(2, 1, 500) * da, rng.gamma(2.2, 1, 500) * db

    def summ(n, d):
        return RatioSummary(
            n=n.size, sum_x=n.sum(), sum_y=d.sum(),
            sum_x2=(n**2).sum(), sum_y2=(d**2).sum(), sum_xy=(n * d).sum(),
        )

    from_raw = ratio_metric_test(na, da, nb, db)
    from_sum = ratio_test_from_summary(summ(na, da), summ(nb, db))
    assert from_sum.p_value == pytest.approx(from_raw.p_value, rel=1e-9)
    assert from_sum.abs_lift == pytest.approx(from_raw.abs_lift)


def test_summary_rejects_too_few_users():
    with pytest.raises(ValueError):
        MomentSummary(n=1, sum_x=1.0, sum_x2=1.0)

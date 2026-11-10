"""Pure statistics engine: no I/O, numpy/scipy only."""

from splitkit.stats.cuped import CupedResult, cuped_ttest
from splitkit.stats.delta import ratio_metric_test
from splitkit.stats.frequentist import TestResult, two_proportion_ztest, welch_ttest
from splitkit.stats.multiple import MultipleTestResult, benjamini_hochberg
from splitkit.stats.power import minimum_detectable_effect, required_sample_size_proportion
from splitkit.stats.sequential import msprt_pvalue, sequential_pvalues
from splitkit.stats.srm import SrmResult, srm_check

__all__ = [
    "CupedResult",
    "MultipleTestResult",
    "SrmResult",
    "TestResult",
    "benjamini_hochberg",
    "cuped_ttest",
    "minimum_detectable_effect",
    "msprt_pvalue",
    "ratio_metric_test",
    "required_sample_size_proportion",
    "sequential_pvalues",
    "srm_check",
    "two_proportion_ztest",
    "welch_ttest",
]

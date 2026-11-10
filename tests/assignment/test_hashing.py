import json
from pathlib import Path

import numpy as np
import pytest
from scipy import stats as sps

from splitkit.assignment import Variant, assign, bucket, fnv1a32

VECTORS = Path(__file__).resolve().parents[1] / "vectors" / "assignment_vectors.json"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", 0x811C9DC5), ("a", 0xE40C292C), ("foobar", 0xBF9CF968)],  # published FNV-1a 32 values
)
def test_fnv1a32_reference_values(text, expected):
    assert fnv1a32(text) == expected


def test_fnv_hashes_utf8_bytes():
    assert fnv1a32("é") != fnv1a32("e")


def test_bucket_in_unit_interval_and_deterministic():
    b = bucket("salt", "user-42")
    assert 0.0 <= b < 1.0
    assert bucket("salt", "user-42") == b
    assert bucket("other", "user-42") != b


AB = (Variant("control", 0.5), Variant("treatment", 0.5))


def test_assignment_is_balanced_on_sequential_ids():
    counts = {"control": 0, "treatment": 0}
    for i in range(100_000):
        counts[assign(AB, "exp-salt", f"user-{i}")] += 1
    p = sps.chisquare(list(counts.values())).pvalue
    assert p > 0.001, counts


def test_unequal_weights_respected():
    variants = (Variant("a", 0.2), Variant("b", 0.3), Variant("c", 0.5))
    n = 60_000
    counts = {"a": 0, "b": 0, "c": 0}
    for i in range(n):
        counts[assign(variants, "w", str(i))] += 1
    p = sps.chisquare(list(counts.values()), [0.2 * n, 0.3 * n, 0.5 * n]).pvalue
    assert p > 0.001, counts


def test_experiments_with_different_salts_are_independent():
    table = np.zeros((2, 2))
    for i in range(40_000):
        a = assign(AB, "exp-one", f"u{i}") == "treatment"
        b = assign(AB, "exp-two", f"u{i}") == "treatment"
        table[int(a), int(b)] += 1
    assert sps.chi2_contingency(table).pvalue > 0.001, table


def test_invalid_variants_rejected():
    with pytest.raises(ValueError):
        assign((Variant("a", 0.5), Variant("b", 0.4)), "s", "u")
    with pytest.raises(ValueError):
        assign((Variant("a", 1.0),), "s", "u")
    with pytest.raises(ValueError):
        assign((Variant("a", 0.5), Variant("a", 0.5)), "s", "u")
    with pytest.raises(ValueError):
        Variant("a", 0.0)


def test_shared_vectors_match():
    """The TypeScript SDK runs the same file; both sides must agree."""
    data = json.loads(VECTORS.read_text())
    for case in data["cases"]:
        variants = tuple(Variant(v["name"], v["weight"]) for v in case["variants"])
        assert assign(variants, case["salt"], case["user_id"]) == case["expected"], case

"""Regenerate tests/vectors/assignment_vectors.json from the Python reference.

Only rerun after an intentional change to the hashing scheme: the TypeScript
SDK tests read this file, so a diff here means existing users would move arms.
"""

import json
from pathlib import Path

from splitkit.assignment import Variant, assign

OUT = Path(__file__).resolve().parents[1] / "tests" / "vectors" / "assignment_vectors.json"
CONFIGS = [
    ("checkout-v2", [("control", 0.5), ("treatment", 0.5)]),
    ("hero-copy", [("a", 0.2), ("b", 0.3), ("c", 0.5)]),
    ("ramp-10pct", [("control", 0.9), ("treatment", 0.1)]),
]
USERS = ["user-1", "user-2", "user-3", "42", "alice@example.com", "émile", "", "user-999999"]


def main() -> None:
    cases = [
        {"salt": salt, "user_id": user, "variants": [{"name": n, "weight": w} for n, w in variants],
         "expected": assign(tuple(Variant(n, w) for n, w in variants), salt, user)}
        for salt, variants in CONFIGS
        for user in USERS
    ]
    OUT.write_text(json.dumps({"scheme": "fnv1a32-double", "cases": cases}, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

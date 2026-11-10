"""Deterministic variant assignment, mirrored byte-for-byte by the TypeScript SDK.

bucket = fnv1a32(str(fnv1a32(f"{salt}:{user_id}"))) / 2**32

The second FNV pass improves avalanche on sequential ids ("user-1", "user-2",
...), which single-pass FNV-1a maps to correlated buckets. Hashing keeps the
hot path free of database lookups: any client with the experiment config
assigns the same user to the same variant.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

FNV_OFFSET = 0x811C9DC5
FNV_PRIME = 0x01000193
UINT32 = 0xFFFFFFFF


@dataclass(frozen=True)
class Variant:
    name: str
    weight: float

    def __post_init__(self) -> None:
        if not 0 < self.weight <= 1:
            raise ValueError(f"variant weight must be in (0, 1], got {self.weight}")


def fnv1a32(text: str) -> int:
    h = FNV_OFFSET
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * FNV_PRIME) & UINT32
    return h


def bucket(salt: str, user_id: str) -> float:
    return fnv1a32(str(fnv1a32(f"{salt}:{user_id}"))) / 2**32


def validate_variants(variants: Sequence[Variant]) -> None:
    if len(variants) < 2:
        raise ValueError("an experiment needs at least 2 variants")
    names = [v.name for v in variants]
    if len(set(names)) != len(names):
        raise ValueError("variant names must be unique")
    if not math.isclose(sum(v.weight for v in variants), 1.0, abs_tol=1e-9):
        raise ValueError("variant weights must sum to 1")


def assign(variants: Sequence[Variant], salt: str, user_id: str) -> str:
    validate_variants(variants)
    b = bucket(salt, user_id)
    cumulative = 0.0
    for v in variants:
        cumulative += v.weight
        if b < cumulative:
            return v.name
    return variants[-1].name  # float round-off guard: b is < 1 but sum may be 0.999...

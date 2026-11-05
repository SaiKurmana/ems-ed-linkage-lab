"""Shared helpers for integration-pattern simulations."""

from __future__ import annotations

import numpy as np


def stage(
    rng: np.random.Generator, ids: list[str], pass_rate: float
) -> tuple[list[str], list[str]]:
    """Exact-count survival sampling.

    Exactly round(pass_rate * len(ids)) ids survive, so the end-to-end carry rate of a chain of
    stages is deterministic up to rounding. Returns (survivors, failures), both sorted.
    """
    ids = sorted(ids)
    k = int(round(pass_rate * len(ids)))
    keep_idx = set(rng.choice(len(ids), size=k, replace=False).tolist()) if k else set()
    survivors = [x for i, x in enumerate(ids) if i in keep_idx]
    failures = [x for i, x in enumerate(ids) if i not in keep_idx]
    return survivors, failures


def expected_carry_rate(pass_rates: list[float]) -> float:
    out = 1.0
    for p in pass_rates:
        out *= p
    return out

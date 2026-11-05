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


def agency_strata(ems, cfg: dict) -> dict[str, str]:
    """EMS UUID -> urbanicity of the responding agency's county ('urban' / 'rural').

    In this synthetic world each county has one agency, and agencies in rural counties stand in
    for "rural / small agencies" in the sensitivity scenario.
    """
    urb = {c["code"]: c["urbanicity"] for c in cfg["geography"]["counties"]}
    return dict(zip(ems.ems_uuid, ems.incident_county.map(urb), strict=True))


def stage_by_stratum(
    rng: np.random.Generator,
    ids: list[str],
    pass_rate: float,
    stage_name: str,
    pattern_cfg: dict,
    strata: dict[str, str],
) -> tuple[list[str], list[str]]:
    """Like `stage`, but a stratum may have its own pass rate.

    `pattern_cfg["stratum_overrides"]` maps stratum -> {stage_name: rate}. With no override for
    this stage the call is exactly `stage(...)` (same RNG draws), so the baseline is unchanged.
    Within each stratum the survivor count is exact, so expected carry per stratum is the
    product of that stratum's pass rates.
    """
    overrides = {
        s: o[stage_name]
        for s, o in (pattern_cfg.get("stratum_overrides") or {}).items()
        if stage_name in o
    }
    if not overrides:
        return stage(rng, ids, pass_rate)
    survivors, failures = [], []
    for s in sorted({strata[i] for i in ids}):
        keep, drop = stage(rng, [i for i in ids if strata[i] == s], overrides.get(s, pass_rate))
        survivors += keep
        failures += drop
    return sorted(survivors), sorted(failures)


def stratum_rate(pattern_cfg: dict, stratum: str, stage_name: str) -> float:
    o = (pattern_cfg.get("stratum_overrides") or {}).get(stratum, {})
    return o.get(stage_name, pattern_cfg[stage_name])

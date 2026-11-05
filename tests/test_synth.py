"""Synthetic generator: determinism, separation of ground truth, standards-shaped values."""

from __future__ import annotations

import re

import pandas as pd

from common.config import deep_merge
from synth import codes
from synth.generate import generate

# NEMSIS v3.5.0 commonTypes_v3.xsd, simpleType "UUID"
NEMSIS_UUID = re.compile(
    r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[1-5][a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}$"
)
# NEMSIS v3.5.0 eInjury.01 (icd10CodeInjury) pattern
NEMSIS_INJURY_ICD = re.compile(r"^([TV-Y][0-9]{2})((\.[0-9A-Z]{1,4})?)$")


def _small(cfg, n=400):
    return deep_merge(cfg, {"population": {"n_events": n}})


def test_generator_is_deterministic(ci_config):
    a, b = generate(_small(ci_config)), generate(_small(ci_config))
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])


def test_different_seed_changes_data(ci_config):
    a = generate(_small(ci_config))
    b = generate(deep_merge(_small(ci_config), {"seed": 7}))
    assert not a["ems_records"].ems_uuid.equals(b["ems_records"].ems_uuid)


def test_uuid_is_v4_and_matches_nemsis_pattern(pipeline):
    u = pipeline["ems"].ems_uuid
    assert u.is_unique
    assert u.map(lambda x: bool(NEMSIS_UUID.match(x))).all()
    assert (u.str[14] == "4").all()  # version 4


def test_ground_truth_is_not_exposed_to_linkage_inputs(pipeline):
    hidden = {"person_id", "event_id", "race_eth", "severity", "alcohol_involved"}
    assert not hidden & set(pipeline["ems"].columns)
    assert not hidden & set(pipeline["ed"].columns)


def test_population_includes_non_transports_and_walkins(pipeline):
    gt = pipeline["gt"]
    assert (gt.ems_called & ~gt.transported).sum() > 0  # non-transported EMS calls
    assert (gt.ed_visit & ~gt.ems_called).sum() > 0  # ED visits with no EMS record
    assert len(pipeline["truth"]) == gt.transported.sum()


def test_codes_are_from_verified_lists(pipeline):
    ed = pipeline["ed"]
    dx = {c for s in ed.dx_codes for c in s.split("|")}
    assert dx <= set(codes.ALL_ICD10CM)
    assert set(ed.external_cause_code) <= set(codes.ALL_ICD10CM)
    for c in pipeline["ems"].cause_of_injury:
        assert NEMSIS_INJURY_ICD.match(codes.dotted(c))
    alc = {v for s in pipeline["ems"].alcohol_drug_indicator for v in s.split("|")}
    assert alc <= set(codes.ALCOHOL_DRUG_POSITIVE) | {"None Reported", "Not Recorded"}


def test_subgroup_differential_error_rates(pipeline):
    gt = pipeline["gt"][pipeline["gt"].ems_called]
    issue = gt.ems_dq_flags.fillna("").str.contains("name_")
    by = issue.groupby(gt.race_eth).mean()
    assert by["Hispanic"] > by["White"]
    race_issue = gt.ems_dq_flags.fillna("").str.contains("race_").groupby(gt.race_eth).mean()
    assert race_issue["AIAN"] > race_issue["White"]

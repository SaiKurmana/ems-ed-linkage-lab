"""Integration patterns: message/bundle validity and the carry-rate regression test."""

from __future__ import annotations

import json

import numpy as np
import pytest
from hl7apy.consts import VALIDATION_LEVEL
from hl7apy.parser import parse_message

from common import EMS_UUID_SYSTEM
from common.config import deep_merge
from common.io import read_json
from linkage.deterministic import link_on_uuid
from linkage.evaluate import metrics
from patterns import hl7v2, pattern_a, pattern_c
from patterns.common import expected_carry_rate, stage
from patterns.pattern_c import validate


def _hl7_files(pipeline):
    return sorted((pipeline["paths"]["examples_dir"]).glob("pattern_[ab]/*.hl7"))


def _wire(path):
    return "\r".join(s for s in path.read_text().splitlines() if not s.startswith("#")) + "\r"


def test_stage_is_exact_count():
    rng = np.random.default_rng(0)
    ids = [f"x{i}" for i in range(1000)]
    keep, drop = stage(rng, ids, 0.873)
    assert len(keep) == 873 and len(drop) == 127 and not set(keep) & set(drop)


def test_hl7_examples_parse_and_validate_strict(pipeline):
    files = _hl7_files(pipeline)
    assert files
    for f in files:
        msg = hl7v2.parse(_wire(f))
        assert hl7v2.message_type(msg).startswith("ADT^")
        parse_message(
            _wire(f), validation_level=VALIDATION_LEVEL.STRICT, find_groups=True
        ).validate()


def test_uuid_lives_in_pv1_50_of_ed_record_messages(pipeline):
    for f in sorted(pipeline["paths"]["examples_dir"].glob("pattern_a/*hospital_ADT_A04.hl7")):
        msg = hl7v2.parse(_wire(f))
        u = hl7v2.extract_ems_uuid(msg)
        assert u and u in set(pipeline["ems"].ems_uuid)
        assert hl7v2.field(msg, "PV1", 50).endswith("^^^EMSUUID^VN")


def test_fhir_examples_validate_and_carry_identifier(pipeline):
    files = sorted(pipeline["paths"]["examples_dir"].glob("pattern_c/*.json"))
    assert files
    for f in files:
        b = validate(json.loads(f.read_text()))
        assert pattern_c.ems_uuid_from_bundle(b) in set(pipeline["ems"].ems_uuid)
        enc = [e.resource for e in b.entry if e.resource.resource_type == "Encounter"][0]
        systems = [i.system for i in enc.identifier]
        assert EMS_UUID_SYSTEM in systems and len(systems) == 2  # hospital id + EMS UUID


def test_invalid_fhir_is_rejected():
    from pydantic import ValidationError

    from patterns.pattern_c import FHIRCodeError

    with pytest.raises(ValidationError):  # missing required Bundle.type
        validate({"resourceType": "Bundle"})
    with pytest.raises(ValidationError):  # unknown element
        validate({"resourceType": "Bundle", "type": "collection", "foo": 1})
    with pytest.raises(FHIRCodeError):  # code outside required value set
        validate({"resourceType": "Bundle", "type": "not-a-bundle-type"})


@pytest.mark.parametrize("pattern", ["A", "C"])
def test_regression_deterministic_recall_equals_configured_carry_rate(pipeline, pattern):
    """Deterministic UUID linkage recall must equal the configured end-to-end carry rate."""
    cfg = pipeline["cfg"]
    key, stages = {
        "A": ("A_point_to_point", pattern_a.STAGES),
        "C": ("C_fhir_api", pattern_c.STAGES),
    }[pattern]
    expected = expected_carry_rate([cfg["patterns"][key][s] for s in stages])
    m = read_json(pipeline["paths"]["results_dir"] / "linkage_metrics.json")["methods"][
        f"det_{pattern}"
    ]
    n = len(pipeline["truth"])
    # exact-count stages: only rounding at each stage can move the result
    assert abs(m["recall"] - expected) <= len(stages) / n + 1e-9
    assert m["precision"] == 1.0 and m["false_positives"] == 0


def test_regression_holds_when_rates_change(pipeline):
    cfg = deep_merge(
        pipeline["cfg"],
        {
            "patterns": {
                "A_point_to_point": {
                    "interface_live": 0.6,
                    "message_delivered": 0.9,
                    "registration_merge": 0.75,
                }
            }
        },
    )
    res = pattern_a.run(
        pipeline["ems"], pipeline["ed"], pipeline["truth"], cfg, np.random.default_rng(1)
    )
    m = metrics(link_on_uuid(pipeline["ems"], res["ed_records"]), pipeline["truth"])
    assert abs(m["recall"] - 0.6 * 0.9 * 0.75) <= 3 / len(pipeline["truth"])


def test_hie_pattern_cannot_exceed_message_availability(pipeline):
    cfg = pipeline["cfg"]["patterns"]["B_hie"]
    m = read_json(pipeline["paths"]["results_dir"] / "linkage_metrics.json")["methods"]["det_B"]
    assert m["recall"] <= cfg["ems_adt_sent"] * cfg["writeback_success"] + 0.01

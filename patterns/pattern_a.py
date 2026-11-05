"""Pattern A — point-to-point HL7 v2.

Flow (simulated):
  1. At or before arrival, the ePCR system sends an ADT^A05 (pre-admit) to the destination
     hospital's interface engine. The EMS UUID travels in PV1-50 (Alternate Visit ID) with
     assigning authority "EMSUUID" (a documented local convention; see docs/architecture.md).
  2. The hospital interface engine parses the message (python-hl7) and holds the pre-admit.
  3. ED registration merges the pre-admit into the ED encounter; the UUID is retained in the
     ED encounter's PV1-50 and appears on the hospital's own ADT^A04 feed.

Failure stages (configurable): interface_live -> message_delivered -> registration_merge.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from patterns import hl7v2 as h
from patterns.common import expected_carry_rate, stage

STAGES = ["interface_live", "message_delivered", "registration_merge"]


def ems_a05(e) -> str:
    """ADT^A05 pre-admit from the ePCR system to the receiving hospital."""
    when = e.left_scene_ts
    return h.join(
        h.msh("EPCR_SYNTH", e.agency_id, "ADT_IN", e.destination_code, when, "A05", "ADT_A05",
              f"{e.pcr_number}-A05"),
        h.evn("A05", when),
        h.pid(e.pcr_number, e.agency_id, "PI", e.patient_last_name, e.patient_first_name,
              e.patient_dob, e.patient_sex, race=e.patient_race),
        h.pv1(location_facility=e.destination_code, ems_uuid=e.ems_uuid),
        h.pv2("A"),
    )


def hospital_a04(r, ems_uuid: str | None) -> str:
    """ADT^A04 (register a patient) emitted by the hospital EHR for every ED registration."""
    return h.join(
        h.msh("EHR_SYNTH", r.hospital_id, "DOWNSTREAM", "WAREHOUSE", r.arrival_ts, "A04", "ADT_A01",
              f"{r.ed_encounter_id}-A04"),
        h.evn("A04", r.arrival_ts),
        h.pid(r.mrn, r.hospital_id, "MR", r.last_name, r.first_name, r.dob, r.sex,
              race=r.race, ethnicity=r.ethnicity),
        h.pv1(location_facility=r.hospital_id, visit_number=r.ed_encounter_id,
              visit_aa=r.hospital_id, admit_ts=r.arrival_ts, ems_uuid=ems_uuid),
        h.pv2(r.arrival_mode),
    )


def run(ems: pd.DataFrame, ed: pd.DataFrame, truth_links: pd.DataFrame, cfg: dict,
        rng: np.random.Generator) -> dict:
    pc = cfg["patterns"]["A_point_to_point"]
    transported = {e.ems_uuid: e for e in ems[ems.destination_code.notna()].itertuples(index=False)}
    ed_rows = {r.ed_encounter_id: r for r in ed.itertuples(index=False)}
    ids = sorted(transported)
    log = {"n_transported": len(ids)}

    live, _ = stage(rng, ids, pc["interface_live"])
    # Build + "send" A05 messages for live interfaces
    delivered, _ = stage(rng, live, pc["message_delivered"])
    # Hospital interface engine parses each delivered message and stores the pre-admit
    pre_admits: dict[str, str] = {}
    for u in delivered:
        msg = h.parse(ems_a05(transported[u]))
        parsed = h.extract_ems_uuid(msg)
        assert parsed == u
        pre_admits[u] = h.field(msg, "PV1", 3)
    merged, _ = stage(rng, sorted(pre_admits), pc["registration_merge"])
    log.update({"interface_live": len(live), "message_delivered": len(delivered),
                "registration_merge": len(merged)})

    # Registration: the clerk merges the pre-admit into the arriving patient's ED encounter
    link_map = truth_links.set_index("ems_uuid").ed_encounter_id
    carried = {link_map[u]: u for u in merged}

    # Hospital emits A04 for each ED encounter; the ED record's UUID is read back from PV1-50
    out_uuid = []
    for r in ed.itertuples(index=False):
        msg = h.parse(hospital_a04(r, carried.get(r.ed_encounter_id)))
        out_uuid.append(h.extract_ems_uuid(msg))
    ed_out = ed.copy()
    ed_out["ems_uuid"] = out_uuid
    log["ed_records_with_uuid"] = int(ed_out.ems_uuid.notna().sum())
    log["expected_carry_rate"] = expected_carry_rate([pc[s] for s in STAGES])
    log["observed_carry_rate"] = len(merged) / max(1, len(ids))

    # examples: pick the first few carried encounters (sorted, deterministic)
    examples = []
    for u in sorted(merged)[: cfg["patterns"]["n_examples"]]:
        e, r = transported[u], ed_rows[link_map[u]]
        examples.append({"ems_a05": h.pretty(ems_a05(e)), "hospital_a04": h.pretty(hospital_a04(r, u))})
    return {"ed_records": ed_out, "log": log, "examples": examples}

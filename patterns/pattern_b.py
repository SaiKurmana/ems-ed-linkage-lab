"""Pattern B — HIE intermediary.

Flow (simulated):
  1. The ePCR system sends an ADT^A04 to the HIE when the PCR is completed. The EMS UUID is
     the EMS "visit number" (PV1-19, assigning authority EMSUUID); PV1-37 carries the
     destination facility; PV1-45 the transfer-of-care time. PCR completion is often delayed.
  2. The ED sends its own ADT^A04 to the HIE at registration.
  3. The HIE's rule-based matcher pairs them: same destination facility, EMS message received
     within the HIE's match window, handoff time within a tolerance of ED arrival, and a
     demographic score (DOB, sex, last-name Soundex, first initial). Ambiguous ties -> no match.
  4. The HIE writes the UUID back to the hospital as an ADT^A08 (update) with PV1-50 populated.

Because step 3 uses demographics, the HIE can MISS links and can also write back the WRONG
UUID (a false match that a downstream deterministic join will faithfully reproduce).
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from common import EMS_UUID_ASSIGNING_AUTHORITY
from patterns import hl7v2 as h
from patterns.common import stage

ALIAS_NAMES = {"UNKNOWN", "TRAUMA", "DOE"}


def soundex(name: str | None) -> str | None:
    if not name:
        return None
    name = "".join(c for c in name.upper() if c.isalpha())
    if not name:
        return None
    codes = {**dict.fromkeys("BFPV", "1"), **dict.fromkeys("CGJKQSXZ", "2"),
             **dict.fromkeys("DT", "3"), "L": "4", **dict.fromkeys("MN", "5"), "R": "6"}
    out, prev = name[0], codes.get(name[0], "")
    for c in name[1:]:
        code = codes.get(c, "")
        if code and code != prev:
            out += code
        if c not in "HW":
            prev = code
    return (out + "000")[:4]


def ems_a04(e, sent_ts) -> str:
    return h.join(
        h.msh("EPCR_SYNTH", e.agency_id, "HIE_SYNTH", "HIE", sent_ts, "A04", "ADT_A01",
              f"{e.pcr_number}-A04"),
        h.evn("A04", sent_ts),
        h.pid(e.pcr_number, e.agency_id, "PI", e.patient_last_name, e.patient_first_name,
              e.patient_dob, e.patient_sex, race=e.patient_race),
        h.pv1(visit_number=e.ems_uuid, visit_aa=EMS_UUID_ASSIGNING_AUTHORITY,
              discharged_to=e.destination_code if isinstance(e.destination_code, str) else None,
              admit_ts=e.arrived_patient_ts, discharge_ts=e.transfer_of_care_ts),
        h.pv2("A") if isinstance(e.destination_code, str) else "",
    )


def ed_a04(r) -> str:
    return h.join(
        h.msh("EHR_SYNTH", r.hospital_id, "HIE_SYNTH", "HIE", r.arrival_ts, "A04", "ADT_A01",
              f"{r.ed_encounter_id}-A04"),
        h.evn("A04", r.arrival_ts),
        h.pid(r.mrn, r.hospital_id, "MR", r.last_name, r.first_name, r.dob, r.sex,
              race=r.race, ethnicity=r.ethnicity),
        h.pv1(location_facility=r.hospital_id, visit_number=r.ed_encounter_id,
              visit_aa=r.hospital_id, admit_ts=r.arrival_ts),
        h.pv2(r.arrival_mode),
    )


def hie_a08(r, ems_uuid, when) -> str:
    return h.join(
        h.msh("HIE_SYNTH", "HIE", "ADT_IN", r.hospital_id, when, "A08", "ADT_A01",
              f"{r.ed_encounter_id}-A08"),
        h.evn("A08", when),
        h.pid(r.mrn, r.hospital_id, "MR", r.last_name, r.first_name, r.dob, r.sex),
        h.pv1(location_facility=r.hospital_id, visit_number=r.ed_encounter_id,
              visit_aa=r.hospital_id, admit_ts=r.arrival_ts, ems_uuid=ems_uuid),
    )


def _writeback_ts(r, received: datetime) -> datetime:
    """HIE writes back shortly after both messages are present."""
    return (max(r.arrival_ts, received) + timedelta(minutes=5)).replace(microsecond=0)


def _v2ts(v: str):
    return datetime.strptime(v, "%Y%m%d%H%M%S") if v else None


def _norm(s):
    return None if s is None or (isinstance(s, float) and pd.isna(s)) else str(s).upper().strip()


def _demo_score(e, r) -> int:
    """HIE MPI-style rule score; names that look like aliases never score."""
    score = 0
    el, rl = _norm(e["last"]), _norm(r["last"])
    ef, rf = _norm(e["first"]), _norm(r["first"])
    if e["dob"] and r["dob"] and e["dob"] == r["dob"]:
        score += 2
    if e["sex"] and r["sex"] and e["sex"] == r["sex"]:
        score += 1
    if el and rl and el not in ALIAS_NAMES and rl not in ALIAS_NAMES and soundex(el) == soundex(rl):
        score += 1
    if ef and rf and el not in ALIAS_NAMES and rl not in ALIAS_NAMES and ef[0] == rf[0]:
        score += 1
    return score


def run(ems: pd.DataFrame, ed: pd.DataFrame, truth_links: pd.DataFrame, cfg: dict,
        rng: np.random.Generator) -> dict:
    pc = cfg["patterns"]["B_hie"]
    ems_rows = {e.ems_uuid: e for e in ems.itertuples(index=False)}
    ed_rows = {r.ed_encounter_id: r for r in ed.itertuples(index=False)}
    log: dict = {"n_ems_records": len(ems_rows), "n_ed_records": len(ed_rows)}

    ems_sent, _ = stage(rng, sorted(ems_rows), pc["ems_adt_sent"])
    ed_sent, _ = stage(rng, sorted(ed_rows), pc["ed_adt_sent"])
    log.update({"ems_adt_sent": len(ems_sent), "ed_adt_sent": len(ed_sent)})

    # --- HIE inbound: parse every message (python-hl7) into the HIE's matching store
    delays = rng.lognormal(np.log(pc["ems_message_delay_median_hours"]), pc["ems_message_delay_sigma"], len(ems_sent))
    ems_store = []
    for u, d in zip(ems_sent, delays, strict=True):
        e = ems_rows[u]
        base = e.transfer_of_care_ts if pd.notna(e.transfer_of_care_ts) else e.left_scene_ts
        received = base + timedelta(hours=float(d))
        m = h.parse(ems_a04(e, received))
        last, _, first = h.field(m, "PID", 5).partition("^")
        pv1_19 = h.field(m, "PV1", 19).split("^")
        ems_store.append({
            "uuid": pv1_19[0], "dest": h.field(m, "PV1", 37) or None,
            "handoff": _v2ts(h.field(m, "PV1", 45)),
            "received": received, "last": last, "first": first,
            "dob": h.field(m, "PID", 7) or None, "sex": h.field(m, "PID", 8) if h.field(m, "PID", 8) != "U" else None,
        })
    # index transported EMS messages by destination, sorted by handoff time
    by_dest: dict[str, list[dict]] = {}
    for c in sorted((c for c in ems_store if c["dest"] and c["handoff"] is not None),
                    key=lambda c: (c["handoff"], c["uuid"])):
        by_dest.setdefault(c["dest"], []).append(c)
    handoffs = {k: [c["handoff"] for c in v] for k, v in by_dest.items()}

    ed_store = []
    for eid in ed_sent:
        m = h.parse(ed_a04(ed_rows[eid]))
        last, _, first = h.field(m, "PID", 5).partition("^")
        ed_store.append({
            "ed_encounter_id": h.field(m, "PV1", 19).split("^")[0], "hosp": h.field(m, "MSH", 4),
            "arrival": _v2ts(h.field(m, "PV1", 44)),
            "last": last, "first": first, "dob": h.field(m, "PID", 7) or None,
            "sex": h.field(m, "PID", 8) if h.field(m, "PID", 8) != "U" else None,
        })
    ed_df = pd.DataFrame(ed_store).sort_values(["arrival", "ed_encounter_id"], kind="mergesort")

    window = timedelta(hours=pc["match_window_hours"])
    tol = timedelta(minutes=pc["time_tolerance_minutes"])
    used: set[str] = set()
    matches: dict[str, str] = {}
    received_at: dict[str, datetime] = {}
    n_late = n_ambiguous = 0
    for r in ed_df.to_dict("records"):
        cand = by_dest.get(r["hosp"])
        if not cand:
            continue
        lo = bisect.bisect_left(handoffs[r["hosp"]], r["arrival"] - tol)
        hi = bisect.bisect_right(handoffs[r["hosp"]], r["arrival"] + tol)
        near = cand[lo:hi]
        if not near:
            continue
        on_time = [c for c in near if c["received"] <= r["arrival"] + window]
        if not on_time:
            n_late += 1
            continue
        scored = [(_demo_score(c, r), c["uuid"], abs((c["handoff"] - r["arrival"]).total_seconds()))
                  for c in on_time if c["uuid"] not in used]
        scored = [x for x in scored if x[0] >= 3]
        if not scored:
            continue
        scored.sort(key=lambda x: (-x[0], x[2], x[1]))
        if len(scored) > 1 and scored[0][0] == scored[1][0] and abs(scored[0][2] - scored[1][2]) < 300:
            n_ambiguous += 1
            continue
        matches[r["ed_encounter_id"]] = scored[0][1]
        received_at[scored[0][1]] = next(c["received"] for c in on_time if c["uuid"] == scored[0][1])
        used.add(scored[0][1])
    written, _ = stage(rng, sorted(matches), pc["writeback_success"])
    log.update({"hie_matches": len(matches), "late_ems_messages_blocking_match": n_late,
                "ambiguous_no_match": n_ambiguous, "writeback_success": len(written)})

    # --- Hospital applies A08 updates; ED record's UUID read from PV1-50
    carried = {}
    for eid in written:
        r = ed_rows[eid]
        m = h.parse(hie_a08(r, matches[eid], _writeback_ts(r, received_at[matches[eid]])))
        carried[eid] = h.extract_ems_uuid(m)
    ed_out = ed.copy()
    ed_out["ems_uuid"] = ed_out.ed_encounter_id.map(carried)
    truth = dict(zip(truth_links.ed_encounter_id, truth_links.ems_uuid, strict=True))
    log["writeback_correct"] = int(sum(truth.get(k) == v for k, v in carried.items()))
    log["writeback_wrong_uuid"] = len(carried) - log["writeback_correct"]
    log["ed_records_with_uuid"] = len(carried)
    log["observed_carry_rate"] = log["writeback_correct"] / max(1, len(truth_links))
    log["ems_delay_hours_median"] = float(np.median(delays))
    log["ems_delay_share_over_window"] = float(np.mean(delays > pc["match_window_hours"]))

    examples = []
    correct = sorted(k for k, v in carried.items() if truth.get(k) == v)
    for eid in correct[: cfg["patterns"]["n_examples"]]:
        r, e = ed_rows[eid], ems_rows[carried[eid]]
        examples.append({
            "ems_a04_to_hie": h.pretty(ems_a04(e, received_at[e.ems_uuid])),
            "ed_a04_to_hie": h.pretty(ed_a04(r)),
            "hie_a08_writeback": h.pretty(hie_a08(r, e.ems_uuid, _writeback_ts(r, received_at[e.ems_uuid]))),
        })
    return {"ed_records": ed_out, "log": log, "examples": examples}

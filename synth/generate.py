"""Synthetic generator: injury events -> EMS ePCR records -> ED encounters (+ ground truth).

Synthetic data — for demonstration only. Every distribution here is a simulation
assumption (see config/default.yaml), not an estimate of any real population.

Usage:  python -m synth.generate --config config/default.yaml
"""

from __future__ import annotations

import argparse
import uuid
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from common import DISCLAIMER
from common.config import load_config, resolve_paths
from common.io import write_json, write_parquet
from synth import codes
from synth.names import NameFactory, name_variant, typo

SEVERITIES = ["minor", "moderate", "severe", "critical"]
RACE_ETH = ["White", "Black", "Hispanic", "Asian", "AIAN", "NHPI"]
PHONETIC = ["ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT", "GOLF", "HOTEL", "INDIA",
            "JULIET", "KILO", "LIMA", "MIKE", "NOVEMBER", "OSCAR", "PAPA", "QUEBEC", "ROMEO",
            "SIERRA", "TANGO", "UNIFORM", "VICTOR", "WHISKEY", "XRAY", "YANKEE", "ZULU"]
ALIAS_DOB = "1900-01-01"   # placeholder DOB used with trauma aliases (a known linkage trap)

ED_RACE = {  # ED registration (OMB-style race + separate ethnicity)
    "White": "White", "Black": "Black or African American", "Asian": "Asian",
    "AIAN": "American Indian or Alaska Native", "NHPI": "Native Hawaiian or Other Pacific Islander",
}


def age_group(age: int) -> str:
    if age < 18:
        return "0-17"
    if age < 45:
        return "18-44"
    if age < 65:
        return "45-64"
    return "65+"


def _sample_age(mech: str, rng: np.random.Generator) -> int:
    if mech == "mvc":
        bands = [(1, 15, 0.05), (16, 24, 0.24), (25, 44, 0.38), (45, 64, 0.24), (65, 92, 0.09)]
    else:
        bands = [(1, 17, 0.08), (18, 44, 0.12), (45, 64, 0.20), (65, 74, 0.24), (75, 84, 0.21), (85, 101, 0.15)]
    p = np.array([b[2] for b in bands])
    lo, hi, _ = bands[rng.choice(len(bands), p=p / p.sum())]
    return int(rng.integers(lo, hi + 1))


def _uuid4(rng: np.random.Generator) -> str:
    return str(uuid.UUID(bytes=rng.bytes(16), version=4))


def _lognormal(rng, median, sigma, size=None):
    return rng.lognormal(np.log(median), sigma, size)


class Generator:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.seed = int(cfg["seed"])
        self.rng = np.random.default_rng(self.seed)
        self.year = int(cfg["synthetic_year"])
        self.counties = pd.DataFrame(cfg["geography"]["counties"])
        self.hospitals = pd.DataFrame(cfg["geography"]["hospitals"])
        self.county_urb = dict(zip(self.counties.code, self.counties.urbanicity, strict=True))
        self.county_hosp = dict(zip(self.counties.code, self.counties.nearest_hospital, strict=True))
        self.hosp_county = dict(zip(self.hospitals.code, self.hospitals.county, strict=True))
        self.hosp_name = dict(zip(self.hospitals.code, self.hospitals.name, strict=True))
        self.critical_access = {h for h, n in self.hosp_name.items() if "critical access" in n}
        self.names = NameFactory(self.seed, self.rng)

    # ------------------------------------------------------------------ persons
    def persons(self, n_persons: int) -> pd.DataFrame:
        cfg, rng = self.cfg["population"], self.rng
        mech_p = cfg["mechanism_share"]
        w = self.counties.weight.to_numpy()
        rows = []
        for pid in range(n_persons):
            mech = "mvc" if rng.random() < mech_p["mvc"] else "fall"
            age = _sample_age(mech, rng)
            p_male = 0.56 if mech == "mvc" else (0.38 if age >= 65 else 0.52)
            sex = "M" if rng.random() < p_male else "F"
            home = self.counties.code.iloc[rng.choice(len(w), p=w / w.sum())]
            mix = cfg["race_eth_mix"][self.county_urb[home]]
            re_p = np.array([mix[k] for k in RACE_ETH])
            race_eth = RACE_ETH[rng.choice(len(RACE_ETH), p=re_p / re_p.sum())]
            first, last = self.names.make(race_eth, sex)
            dob = date(self.year, 1, 1) - timedelta(days=int(age * 365.25 + rng.integers(0, 365)))
            rows.append(dict(person_id=f"P{pid:06d}", primary_mechanism=mech, sex=sex,
                             home_county=home, race_eth=race_eth, first_name=first,
                             last_name=last, dob=dob))
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ events
    def events(self, persons: pd.DataFrame) -> pd.DataFrame:
        cfg, rng = self.cfg, self.rng
        n_events = int(cfg["population"]["n_events"])
        n_p = len(persons)
        idx = list(range(n_p))
        # repeat events: frequent fallers (older adults over-weighted)
        ages_ref = np.array([(date(self.year, 7, 1) - d).days / 365.25 for d in persons.dob])
        wt = np.where(ages_ref >= 65, 4.0, 1.0)
        extra = rng.choice(n_p, size=n_events - n_p, replace=True, p=wt / wt.sum())
        idx += list(extra)
        mvc_hours = np.array([2, 2, 1, 1, 1, 2, 4, 7, 7, 5, 4, 5, 6, 6, 6, 7, 8, 8, 7, 5, 4, 4, 3, 3], float)
        fall_hours = np.array([1, 1, 1, 1, 1, 2, 3, 5, 7, 8, 8, 8, 7, 7, 7, 7, 6, 6, 5, 4, 3, 2, 2, 1], float)
        home_share = cfg["population"]["home_county_incident_share"]
        w = self.counties.weight.to_numpy()
        rows = []
        for eid, pi in enumerate(idx):
            p = persons.iloc[pi]
            mech = p.primary_mechanism if eid < n_p else "fall"
            day = date(self.year, 1, 1) + timedelta(days=int(rng.integers(0, 366 if self.year % 4 == 0 else 365)))
            hrs = mvc_hours if mech == "mvc" else fall_hours
            hour = int(rng.choice(24, p=hrs / hrs.sum()))
            event_ts = datetime(day.year, day.month, day.day, hour, int(rng.integers(0, 60)))
            age = int((day - p.dob).days // 365.25)
            if rng.random() < home_share:
                county = p.home_county
            else:
                county = self.counties.code.iloc[rng.choice(len(w), p=w / w.sum())]
            if mech == "mvc":
                sev_p = [0.52, 0.30, 0.13, 0.05]
            elif age >= 65:
                sev_p = [0.38, 0.37, 0.21, 0.04]
            else:
                sev_p = [0.62, 0.28, 0.08, 0.02]
            severity = SEVERITIES[rng.choice(4, p=sev_p)]
            alc = cfg["alcohol_drug"]["base_rate"][mech]
            if mech == "mvc":
                alc *= 1.6 if 21 <= age < 45 else (0.3 if age < 16 else 1.0)
                alc *= 2.0 if (hour >= 21 or hour < 4) else 1.0
            else:
                alc *= 1.8 if 45 <= age < 65 else (0.6 if age >= 65 else (0.2 if age < 18 else 1.0))
            rows.append(dict(event_id=f"EV{eid:06d}", person_id=p.person_id, mechanism=mech,
                             event_ts=event_ts, age=age, incident_county=county,
                             severity=severity, alcohol_involved=bool(rng.random() < min(alc, 0.8))))
        ev = pd.DataFrame(rows)
        return ev.merge(persons, on="person_id", how="left")

    # ------------------------------------------------------------------ EMS + ED clinical flow
    def clinical(self, ev: pd.DataFrame) -> pd.DataFrame:
        cfg, rng = self.cfg, self.rng
        ems_cfg, ed_cfg = cfg["ems"], cfg["ed"]
        trauma_center = cfg["geography"]["trauma_center"]
        out = []
        for r in ev.itertuples(index=False):
            urb = self.county_urb[r.incident_county]
            sev_i = SEVERITIES.index(r.severity)
            p_call = [ems_cfg["call_rate"][r.mechanism], 0.85, 0.97, 0.995][sev_i]
            if r.mechanism == "fall" and r.age >= 65:
                p_call = min(1.0, p_call * 1.15)
            ems_called = rng.random() < p_call
            transported = bool(ems_called and rng.random() < ems_cfg["transport_rate"][r.severity])
            ed_visit = transported or (not ems_called and rng.random() < ed_cfg["seek_care_without_ems"][r.severity])
            d = dict(event_id=r.event_id, ems_called=ems_called, transported=transported, ed_visit=ed_visit)
            # destination
            near = self.county_hosp[r.incident_county]
            if transported and (r.severity == "critical" or (r.severity == "severe" and rng.random() < 0.6)):
                dest = trauma_center
            elif not transported and rng.random() < 0.12:
                dest = self.hospitals.code.iloc[rng.integers(len(self.hospitals))]
            else:
                dest = near
            d["hospital"] = dest if ed_visit else None
            # EMS times
            if ems_called:
                notified = r.event_ts + timedelta(minutes=float(rng.uniform(1, 8)))
                scene = notified + timedelta(minutes=float(_lognormal(rng, ems_cfg["response_minutes"][urb], 0.35)))
                at_pt = scene + timedelta(minutes=float(rng.uniform(0.5, 3)))
                left = at_pt + timedelta(minutes=float(_lognormal(rng, 18 if r.mechanism == "mvc" else 14, 0.3)))
                d.update(unit_notified_ts=notified, arrived_scene_ts=scene, arrived_patient_ts=at_pt,
                         left_scene_ts=left)
                if transported:
                    tmin = _lognormal(rng, ems_cfg["transport_minutes"][urb], 0.3)
                    if dest == trauma_center and self.hosp_county[dest] != r.incident_county:
                        tmin += ems_cfg["transport_minutes"]["to_trauma_center_extra"] * (2.0 if urb == "rural" else 1.0)
                    arr = left + timedelta(minutes=float(tmin))
                    d.update(arrived_destination_ts=arr,
                             transfer_of_care_ts=arr + timedelta(minutes=float(rng.uniform(5, 25))))
            # ED arrival
            if ed_visit:
                if transported:
                    lo, hi = ed_cfg["registration_lag_minutes"]
                    d["ed_arrival_ts"] = d["arrived_destination_ts"] + timedelta(minutes=float(rng.uniform(lo, hi)))
                    d["arrival_mode"] = "A"   # HL7 table 0430: Ambulance
                else:
                    delay = max(15.0, float(_lognormal(rng, ed_cfg["private_arrival_delay_minutes"][r.mechanism], 0.8)))
                    d["ed_arrival_ts"] = r.event_ts + timedelta(minutes=delay)
                    d["arrival_mode"] = "C" if rng.random() < 0.93 else "F"  # Car / On foot
            out.append(d)
        cl = pd.DataFrame(out)
        for c in ("unit_notified_ts", "arrived_scene_ts", "arrived_patient_ts", "left_scene_ts",
                  "arrived_destination_ts", "transfer_of_care_ts", "ed_arrival_ts"):
            cl[c] = pd.to_datetime(cl[c]).dt.floor("s")
        return ev.merge(cl, on="event_id", how="left")

    def vitals_and_findings(self, df: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        recs = []
        for r in df.itertuples(index=False):
            sev = r.severity
            gcs = {"minor": lambda: 15 if rng.random() < 0.95 else 14,
                   "moderate": lambda: int(rng.choice([15, 14, 13], p=[0.7, 0.2, 0.1])),
                   "severe": lambda: int(rng.integers(9, 16)),
                   "critical": lambda: int(rng.integers(3, 13))}[sev]()
            sbp_mu = {"minor": 138, "moderate": 136, "severe": 120, "critical": 96}[sev] + (8 if r.age >= 65 else 0)
            sbp = int(np.clip(rng.normal(sbp_mu, 18 if sev != "critical" else 26), 50, 230))
            hr = int(np.clip(rng.normal({"minor": 86, "moderate": 92, "severe": 104, "critical": 118}[sev], 14), 35, 190))
            rr = int(np.clip(rng.normal({"minor": 16, "moderate": 18, "severe": 20, "critical": 24}[sev], 3 if sev != "critical" else 8), 4, 48))
            # eInjury.03 high-risk criteria
            hi = []
            if gcs <= 8:
                hi.append(codes.TRAUMA_HIGH_RISK["gcs"])
            if r.age >= 65 and sbp < 110:
                hi.append(codes.TRAUMA_HIGH_RISK["sbp_65"])
            if 10 <= r.age < 65 and sbp < 90:
                hi.append(codes.TRAUMA_HIGH_RISK["sbp_adult"])
            if rr < 10 or rr > 29:
                hi.append(codes.TRAUMA_HIGH_RISK["rr"])
            p_anat = {"minor": 0.0, "moderate": 0.04, "severe": 0.35, "critical": 0.6}[sev]
            if rng.random() < p_anat:
                k = rng.choice(["skull", "chest", "pelvis", "long_bones"])
                hi.append(codes.TRAUMA_HIGH_RISK[str(k)])
            # eInjury.04 moderate-risk criteria
            mod = []
            p_mod = {"minor": 0.03, "moderate": 0.15, "severe": 0.45, "critical": 0.6}[sev]
            if rng.random() < p_mod:
                opts = codes.TRAUMA_MODERATE_RISK[r.mechanism]
                if r.mechanism == "fall":
                    opts = [o for o in opts if (("older adults" in o and r.age >= 65) or "older adults" not in o)]
                mod.append(opts[rng.integers(len(opts))])
            if r.mechanism == "fall" and r.age >= 65 and rng.random() < 0.18:
                mod.append("Anticoagulant use")
            if rng.random() < 0.04:
                mod.append(codes.TRAUMA_MODERATE_RISK["any"][0])
            # eHistory.17 alcohol/drug indicators as documented by EMS
            if rng.random() < 0.03:
                alc = codes.NEMSIS_NOT_RECORDED
            elif (r.alcohol_involved and rng.random() < 0.8) or (not r.alcohol_involved and rng.random() < 0.01):
                k = int(rng.integers(1, 3))
                alc = "|".join(sorted(rng.choice(codes.ALCOHOL_DRUG_POSITIVE, size=k, replace=False)))
            else:
                alc = codes.ALCOHOL_DRUG_NONE
            # procedures (simplified labels)
            procs = ["Cardiac monitoring"] if sev in ("severe", "critical") else []
            if r.mechanism == "mvc" and rng.random() < 0.45 + 0.1 * SEVERITIES.index(sev):
                procs.append("Spinal motion restriction")
            if sev != "minor" and rng.random() < 0.5:
                procs.append("Splinting")
            if sev in ("severe", "critical") or rng.random() < 0.15:
                procs.append("Peripheral IV access")
            if rng.random() < 0.2:
                procs.append("Bleeding control / wound care")
            if gcs <= 8:
                procs.append("Airway management")
            if sev != "minor" and rng.random() < 0.4:
                procs.append("Pain management (medication)")
            recs.append(dict(event_id=r.event_id, gcs=gcs, sbp=sbp, hr=hr, rr=rr,
                             trauma_high_risk="|".join(dict.fromkeys(hi)) or codes.NONE_REPORTED,
                             trauma_moderate_risk="|".join(dict.fromkeys(mod)) or codes.NONE_REPORTED,
                             alcohol_drug_indicator=alc,
                             procedures="|".join(sorted(set(procs))) if procs else ""))
        return df.merge(pd.DataFrame(recs), on="event_id", how="left")

    def ed_outcomes(self, df: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        recs = []
        for r in df.itertuples(index=False):
            if not r.ed_visit:
                recs.append(dict(event_id=r.event_id))
                continue
            p = np.array({"minor": [0.95, 0.04, 0.01, 0.0], "moderate": [0.62, 0.30, 0.077, 0.003],
                          "severe": [0.15, 0.67, 0.16, 0.02], "critical": [0.02, 0.60, 0.24, 0.14]}[r.severity])
            if r.mechanism == "fall" and r.age >= 65:
                p[1] *= 1.25
            if r.hospital in self.critical_access and r.severity in ("severe", "critical"):
                p[2] += 0.7 * p[1]
                p[1] *= 0.3
            disp = codes.ED_DISPOSITIONS[rng.choice(4, p=p / p.sum())]
            pool = dict(codes.INJURY_DX[r.severity])
            pref = codes.FALL_PREFERRED if r.mechanism == "fall" else codes.MVC_PREFERRED
            keys = sorted(pool)
            wts = np.array([3.0 if k in pref else 1.0 for k in keys])
            dx = [keys[rng.choice(len(keys), p=wts / wts.sum())]]
            if r.severity != "minor" and rng.random() < 0.35:
                lower = sorted(codes.INJURY_DX[SEVERITIES[SEVERITIES.index(r.severity) - 1]])
                dx.append(lower[rng.integers(len(lower))])
            ext = list(codes.EXTERNAL_CAUSE[r.mechanism])
            ext_w = np.array(codes.EXTERNAL_CAUSE_WEIGHTS[r.mechanism])
            ecode = ext[rng.choice(len(ext), p=ext_w / ext_w.sum())]
            recs.append(dict(event_id=r.event_id, ed_disposition=disp, dx_codes="|".join(dx),
                             external_cause_code=ecode))
        return df.merge(pd.DataFrame(recs), on="event_id", how="left")

    # ------------------------------------------------------------------ data quality
    def _rate(self, side: str, key: str, r) -> float:
        dq = self.cfg["data_quality"]
        rate = dq[side][key]
        m = dq["multipliers"]
        rate *= m["race_eth"].get(r.race_eth, {}).get(key, 1.0)
        rate *= m["age_group"].get(age_group(r.age), {}).get(key, 1.0)
        if side == "ems":
            rate *= m["urbanicity"].get(self.county_urb[r.incident_county], {}).get(key, 1.0)
            if r.alcohol_involved:
                rate *= m["alcohol_involved"].get(key, 1.0)
        return min(rate, dq["max_rate"])

    def _dob_error(self, dob: date, side: str) -> date:
        rng = self.rng
        kind = rng.integers(4 if side == "ems" else 3)
        if kind == 0 and dob.day <= 12 and dob.day != dob.month:
            return date(dob.year, dob.day, dob.month)
        if kind == 1:
            try:
                return dob.replace(year=dob.year + int(rng.choice([-1, 1])))
            except ValueError:
                return dob.replace(year=dob.year + 1, day=28)
        if kind == 3:  # EMS estimated age -> Jan 1 of estimated birth year
            return date(dob.year + int(rng.integers(-2, 3)), 1, 1)
        d = dob + timedelta(days=int(rng.choice([-10, -9, -1, 1, 9, 10])))
        return d

    def corrupt(self, df: pd.DataFrame, side: str) -> pd.DataFrame:
        rng = self.rng
        dq = self.cfg["data_quality"][side]
        recs = []
        for r in df.itertuples(index=False):
            first, last, dob, sex, re = r.first_name, r.last_name, r.dob, r.sex, r.race_eth
            flags = []
            if rng.random() < self._rate(side, "name_variant", r):
                first, last = name_variant(first, last, r.race_eth, rng)
                flags.append("name_variant")
            if rng.random() < self._rate(side, "name_typo", r):
                if rng.random() < 0.5:
                    first = typo(first, rng)
                else:
                    last = typo(last, rng)
                flags.append("name_typo")
            if rng.random() < self._rate(side, "dob_missing", r):
                dob = None
                flags.append("dob_missing")
            elif rng.random() < self._rate(side, "dob_error", r):
                dob = self._dob_error(dob, side)
                flags.append("dob_error")
            if rng.random() < self._rate(side, "race_misclass", r):
                if re == "White":
                    re = "Hispanic" if rng.random() < 0.5 else "Black"
                else:
                    re = "White" if rng.random() < 0.8 else RACE_ETH[rng.integers(len(RACE_ETH))]
                flags.append("race_misclass")
            if rng.random() < self._rate(side, "race_unknown", r):
                re = None
                flags.append("race_unknown")
            if rng.random() < dq["sex_missing"]:
                sex = None
                flags.append("sex_missing")
            # unidentified / alias registrations (severity-dependent)
            if side == "ems" and rng.random() < dq["unidentified"][r.severity]:
                first, last, dob, re = "UNKNOWN", "UNKNOWN", None, None
                flags.append("unidentified")
            if side == "ed" and rng.random() < dq["trauma_alias"][r.severity]:
                first, last, dob, re = PHONETIC[rng.integers(len(PHONETIC))], "TRAUMA", ALIAS_DOB, None
                flags.append("trauma_alias")
            recs.append(dict(event_id=r.event_id, first=first, last=last,
                             dob=dob if isinstance(dob, str) else (dob.isoformat() if dob else None),
                             sex=sex, race_eth_rec=re, dq_flags="|".join(flags)))
        return pd.DataFrame(recs)

    # ------------------------------------------------------------------ assemble outputs
    def run(self) -> dict[str, pd.DataFrame]:
        cfg = self.cfg
        n_events = int(cfg["population"]["n_events"])
        n_persons = n_events - int(round(n_events * cfg["population"]["repeat_event_rate"]))
        persons = self.persons(n_persons)
        ev = self.events(persons)
        ev = self.clinical(ev)
        ev = self.vitals_and_findings(ev)
        ev = self.ed_outcomes(ev)
        ev = ev.sort_values(["event_ts", "event_id"], kind="mergesort").reset_index(drop=True)

        ems_src = ev[ev.ems_called].copy()
        ed_src = ev[ev.ed_visit].copy()
        ems_dq = self.corrupt(ems_src, "ems")
        ed_dq = self.corrupt(ed_src, "ed")

        # ---- EMS ePCR records (simplified NEMSIS-inspired) ----
        ems_src["ems_uuid"] = [_uuid4(self.rng) for _ in range(len(ems_src))]
        ems_src["agency_id"] = "E" + ems_src.incident_county.str[1:]
        ems_src["pcr_seq"] = ems_src.groupby("agency_id").cumcount() + 1
        ems_src["pcr_number"] = ems_src.agency_id + f"-{self.year}-" + ems_src.pcr_seq.map(lambda x: f"{x:06d}")
        ems = ems_src.merge(ems_dq, on="event_id")
        ems["transport_disposition"] = np.where(
            ems.transported, codes.TRANSPORT_THIS_UNIT,
            np.where(self.rng.random(len(ems)) < 0.7, codes.PATIENT_REFUSED, codes.NO_TRANSPORT))
        ems["unit_disposition"] = codes.PATIENT_CONTACT
        ems["destination_code"] = np.where(ems.transported, ems.hospital, None)
        ems["cause_of_injury"] = [
            list(codes.EXTERNAL_CAUSE[m])[self.rng.choice(len(codes.EXTERNAL_CAUSE[m]), p=np.array(codes.EXTERNAL_CAUSE_WEIGHTS[m]) / sum(codes.EXTERNAL_CAUSE_WEIGHTS[m]))]
            for m in ems.mechanism]
        ems["race"] = ems.race_eth_rec.map(codes.NEMSIS_RACE).fillna(codes.NEMSIS_NOT_RECORDED)
        ems["sex_rec"] = ems.sex_y.map({"F": "Female", "M": "Male"}).fillna("Unknown")
        est_age = ems.age + np.where(ems.dq_flags.str.contains("unidentified"), self.rng.integers(-8, 9, len(ems)), 0)
        ems["age_rec"] = np.clip(est_age, 0, 105)
        ems_out = pd.DataFrame({
            "ems_uuid": ems.ems_uuid, "pcr_number": ems.pcr_number, "agency_id": ems.agency_id,
            "incident_county": ems.incident_county,
            "unit_notified_ts": ems.unit_notified_ts, "arrived_scene_ts": ems.arrived_scene_ts,
            "arrived_patient_ts": ems.arrived_patient_ts, "left_scene_ts": ems.left_scene_ts,
            "arrived_destination_ts": ems.arrived_destination_ts, "transfer_of_care_ts": ems.transfer_of_care_ts,
            "mechanism": ems.mechanism, "cause_of_injury": ems.cause_of_injury,
            "trauma_high_risk": ems.trauma_high_risk, "trauma_moderate_risk": ems.trauma_moderate_risk,
            "alcohol_drug_indicator": ems.alcohol_drug_indicator,
            "sbp": ems.sbp, "hr": ems.hr, "rr": ems.rr, "gcs": ems.gcs, "procedures": ems.procedures,
            "unit_disposition": ems.unit_disposition, "transport_disposition": ems.transport_disposition,
            "destination_code": ems.destination_code,
            "patient_last_name": ems["last"], "patient_first_name": ems["first"],
            "patient_dob": ems.dob_y, "patient_age": ems.age_rec, "patient_sex": ems.sex_rec,
            "patient_race": ems.race, "patient_home_county": ems.home_county,
        })

        # ---- ED encounters ----
        ed = ed_src.merge(ed_dq, on="event_id")
        ed = ed.sort_values(["ed_arrival_ts", "event_id"], kind="mergesort").reset_index(drop=True)
        ed["visit_seq"] = ed.groupby("hospital").cumcount() + 1
        ed["ed_encounter_id"] = ed.hospital + "V" + ed.visit_seq.map(lambda x: f"{x:07d}")
        # MRNs: assigned sequentially per hospital in order of a person's first visit there
        mrn_map: dict[tuple[str, str], str] = {}
        counters: dict[str, int] = {}
        for h, p in zip(ed.hospital, ed.person_id, strict=True):
            if (h, p) not in mrn_map:
                counters[h] = counters.get(h, 0) + 1
                mrn_map[(h, p)] = f"{h}M{counters[h]:07d}"
        ed["mrn"] = [mrn_map[(h, p)] for h, p in zip(ed.hospital, ed.person_id, strict=True)]
        hisp = ed.race_eth_rec == "Hispanic"
        ed_race = ed.race_eth_rec.map(ED_RACE)
        ed_race = ed_race.where(~hisp, np.where(self.rng.random(len(ed)) < 0.4, "White", "Other Race"))
        ed["race"] = ed_race.fillna("Unknown")
        ed["ethnicity"] = np.where(hisp, "Hispanic or Latino",
                                   np.where(ed.race_eth_rec.isna(), "Unknown", "Not Hispanic or Latino"))
        ed_out = pd.DataFrame({
            "ed_encounter_id": ed.ed_encounter_id, "mrn": ed.mrn, "hospital_id": ed.hospital,
            "hospital_county": ed.hospital.map(self.hosp_county), "arrival_ts": ed.ed_arrival_ts,
            "arrival_mode": ed.arrival_mode, "last_name": ed["last"], "first_name": ed["first"],
            "dob": ed.dob_y, "sex": ed.sex_y.fillna("U"), "race": ed.race, "ethnicity": ed.ethnicity,
            "home_county": ed.home_county, "dx_codes": ed.dx_codes,
            "external_cause_code": ed.external_cause_code, "disposition": ed.ed_disposition,
        })

        # ---- ground truth (kept separately; never given to linkage methods) ----
        truth = ev[["event_id", "person_id", "mechanism", "severity", "event_ts", "age", "sex",
                    "race_eth", "first_name", "last_name", "dob", "incident_county", "home_county",
                    "alcohol_involved", "ems_called", "transported", "ed_visit"]].copy()
        truth["dob"] = truth.dob.map(lambda d: d.isoformat())
        truth["age_group"] = truth.age.map(age_group)
        truth["urbanicity"] = truth.incident_county.map(self.county_urb)
        truth = truth.merge(ems[["event_id", "ems_uuid"]], on="event_id", how="left")
        truth = truth.merge(ed[["event_id", "ed_encounter_id", "arrival_mode"]], on="event_id", how="left")
        truth = truth.merge(ems[["event_id", "dq_flags"]].rename(columns={"dq_flags": "ems_dq_flags"}), on="event_id", how="left")
        truth = truth.merge(ed[["event_id", "dq_flags"]].rename(columns={"dq_flags": "ed_dq_flags"}), on="event_id", how="left")
        links = truth[truth.transported][["ems_uuid", "ed_encounter_id"]].copy()

        ems_out = ems_out.sort_values("ems_uuid").reset_index(drop=True)
        ed_out = ed_out.sort_values("ed_encounter_id").reset_index(drop=True)
        return {"ems_records": ems_out, "ed_encounters": ed_out, "ground_truth": truth,
                "truth_links": links}


def profile(out: dict[str, pd.DataFrame], cfg: dict) -> dict:
    t = out["ground_truth"]
    ems_t = t[t.ems_called]
    ed_t = t[t.ed_visit]

    def flag_rates(df, col, by):
        res = {}
        for g, sub in df.groupby(by):
            f = sub[col].fillna("")
            res[str(g)] = {
                "n": int(len(sub)),
                "any_name_issue": float((f.str.contains("name_") | f.str.contains("unidentified") | f.str.contains("trauma_alias")).mean()),
                "dob_issue": float(f.str.contains("dob_").mean()),
                "race_unknown_or_misclassified": float(f.str.contains("race_").mean()),
            }
        return res

    return {
        "disclaimer": DISCLAIMER,
        "seed": cfg["seed"],
        "counts": {
            "injury_events": int(len(t)),
            "persons": int(t.person_id.nunique()),
            "ems_records": int(len(out["ems_records"])),
            "ems_transported": int(t.transported.sum()),
            "ems_not_transported": int((t.ems_called & ~t.transported).sum()),
            "ed_encounters": int(len(out["ed_encounters"])),
            "ed_without_ems": int((t.ed_visit & ~t.transported).sum()),
            "true_links": int(len(out["truth_links"])),
            "mvc_events": int((t.mechanism == "mvc").sum()),
            "fall_events": int((t.mechanism == "fall").sum()),
        },
        "ems_data_quality_by_race_eth": flag_rates(ems_t, "ems_dq_flags", "race_eth"),
        "ed_data_quality_by_race_eth": flag_rates(ed_t, "ed_dq_flags", "race_eth"),
        "ems_data_quality_by_age_group": flag_rates(ems_t, "ems_dq_flags", "age_group"),
        "ems_data_quality_by_urbanicity": flag_rates(ems_t, "ems_dq_flags", "urbanicity"),
    }


def generate(cfg: dict) -> dict[str, pd.DataFrame]:
    return Generator(cfg).run()


def save(out: dict[str, pd.DataFrame], cfg: dict) -> None:
    paths = resolve_paths(cfg)
    raw = paths["data_dir"] / "raw"
    write_parquet(out["ems_records"], raw / "ems_records.parquet", "ems_uuid")
    write_parquet(out["ed_encounters"], raw / "ed_encounters.parquet", "ed_encounter_id")
    write_parquet(out["ground_truth"], raw / "ground_truth.parquet", "event_id")
    write_parquet(out["truth_links"], raw / "truth_links.parquet", "ems_uuid")
    write_json(profile(out, cfg), paths["results_dir"] / "data_profile.json")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = generate(cfg)
    save(out, cfg)
    c = profile(out, cfg)["counts"]
    print(f"[synth] {DISCLAIMER}")
    for k, v in c.items():
        print(f"  {k:>22}: {v}")


if __name__ == "__main__":
    main()

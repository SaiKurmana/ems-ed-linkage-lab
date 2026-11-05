"""Standardise EMS and ED records into a common linkage schema.

Both sides are cleaned the same way a careful real-world pipeline would: upper-case, strip
accents and punctuation, null out known placeholder values (UNKNOWN names, trauma aliases,
1900-01-01 DOBs) and harmonise race/ethnicity (NEMSIS combines Hispanic or Latino into
ePatient.14 Race, whereas ED registration records race and ethnicity separately).
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from synth.codes import NEMSIS_RACE

PLACEHOLDER_NAMES = {"UNKNOWN", "UNK", "DOE", "TRAUMA", "JOHN DOE", "JANE DOE"}
PLACEHOLDER_DOBS = {"1900-01-01"}
NEMSIS_TO_CAT = {v: k for k, v in NEMSIS_RACE.items()}
ED_RACE_TO_CAT = {
    "White": "White",
    "Black or African American": "Black",
    "Asian": "Asian",
    "American Indian or Alaska Native": "AIAN",
    "Native Hawaiian or Other Pacific Islander": "NHPI",
}
COLUMNS = [
    "unique_id",
    "first_name",
    "last_name",
    "dob",
    "sex",
    "race_eth",
    "county",
    "ts",
    "arrival_date",
]


def clean_name(s) -> str | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z ]", " ", s.upper().replace("-", " "))
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def _null_aliases(df: pd.DataFrame) -> pd.DataFrame:
    alias = df.last_name.isin(PLACEHOLDER_NAMES) | df.first_name.isin(PLACEHOLDER_NAMES)
    df.loc[alias, ["first_name", "last_name"]] = None
    df.loc[df.dob.isin(PLACEHOLDER_DOBS), "dob"] = None
    return df


def prep_ems(ems: pd.DataFrame) -> pd.DataFrame:
    ts = ems.arrived_destination_ts.fillna(ems.arrived_patient_ts)
    df = pd.DataFrame(
        {
            "unique_id": ems.ems_uuid,
            "first_name": ems.patient_first_name.map(clean_name),
            "last_name": ems.patient_last_name.map(clean_name),
            "dob": ems.patient_dob,
            "sex": ems.patient_sex.map({"Female": "F", "Male": "M"}),
            "race_eth": ems.patient_race.map(NEMSIS_TO_CAT),
            "county": ems.incident_county,
            "ts": ts,
            "arrival_date": ts.dt.strftime("%Y-%m-%d"),
        }
    )
    return (
        _null_aliases(df)[COLUMNS]
        .astype(object)
        .where(lambda d: d.notna(), None)
        .assign(ts=ts.values)
    )


def prep_ed(ed: pd.DataFrame) -> pd.DataFrame:
    race = ed.race.map(ED_RACE_TO_CAT)
    race = race.where(ed.ethnicity != "Hispanic or Latino", "Hispanic")
    df = pd.DataFrame(
        {
            "unique_id": ed.ed_encounter_id,
            "first_name": ed.first_name.map(clean_name),
            "last_name": ed.last_name.map(clean_name),
            "dob": ed.dob,
            "sex": ed.sex.map({"F": "F", "M": "M"}),
            "race_eth": race,
            "county": ed.hospital_county,
            "ts": ed.arrival_ts,
            "arrival_date": ed.arrival_ts.dt.strftime("%Y-%m-%d"),
        }
    )
    return (
        _null_aliases(df)[COLUMNS]
        .astype(object)
        .where(lambda d: d.notna(), None)
        .assign(ts=ed.arrival_ts.values)
    )

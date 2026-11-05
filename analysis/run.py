"""Demonstration analyses that EMS–ED linkage makes possible.

Synthetic data — for demonstration only. These are illustrations of WHAT CAN BE ASKED once
records are linked, not findings about any real population. Each question is answered three
ways so the effect of the linkage method is visible:
  truth        ground-truth links (only possible in a simulation)
  det_C        deterministic UUID join (Pattern C, FHIR identifier)
  splink_time  probabilistic linkage (Splink)

Usage:  python -m analysis.run --config config/default.yaml
"""

from __future__ import annotations

import argparse

import duckdb
import pandas as pd

from common import DISCLAIMER
from common.config import load_config, resolve_paths
from common.io import write_csv, write_json

LINK_SOURCES = {
    "truth": "Ground truth (simulation only)",
    "det_C": "Deterministic UUID (Pattern C)",
    "splink_time": "Probabilistic (Splink)",
}
CONFOUNDING_NOTE = (
    "Descriptive only. Patients who arrive by EMS differ systematically from those who arrive "
    "privately (injury severity, age, mechanism, time of day, access to transport). Differences "
    "in outcomes must not be read as effects of EMS transport."
)


def _con(paths, src: str) -> duckdb.DuckDBPyConnection:
    raw = paths["data_dir"] / "raw"
    con = duckdb.connect()
    con.execute(
        f"CREATE VIEW ems AS SELECT * FROM read_parquet('{(raw / 'ems_records.parquet').as_posix()}')"
    )
    con.execute(
        f"CREATE VIEW ed AS SELECT * FROM read_parquet('{(raw / 'ed_encounters.parquet').as_posix()}')"
    )
    links = (
        raw / "truth_links.parquet"
        if src == "truth"
        else paths["data_dir"] / "linked" / f"{src}.parquet"
    )
    con.execute(
        f"CREATE VIEW links AS SELECT ems_uuid, ed_encounter_id FROM read_parquet('{links.as_posix()}')"
    )
    con.execute("""
        CREATE VIEW counties AS SELECT * FROM (VALUES
          ('C01','urban'),('C02','urban'),('C03','urban'),('C04','urban'),('C05','rural'),('C06','rural'),
          ('C07','rural'),('C08','rural'),('C09','rural'),('C10','rural'),('C11','rural'),('C12','rural'))
          t(code, urbanicity)""")
    con.execute("""
        CREATE VIEW ed_mech AS SELECT *, CASE WHEN external_cause_code LIKE 'V%' THEN 'MVC'
                                               ELSE 'Fall' END AS mechanism FROM ed""")
    con.execute("""
        CREATE VIEW linked AS
        SELECT d.*, e.alcohol_drug_indicator, e.trauma_high_risk, e.unit_notified_ts, e.incident_county,
               c.urbanicity, e.gcs
        FROM ed_mech d JOIN links l USING (ed_encounter_id) JOIN ems e ON e.ems_uuid = l.ems_uuid
        JOIN counties c ON c.code = e.incident_county""")
    return con


def q1_alcohol(con) -> pd.DataFrame:
    return con.execute("""
        WITH all_ed AS (SELECT mechanism, count(*) AS ed_visits FROM ed_mech GROUP BY 1),
             lk AS (SELECT mechanism, count(*) AS linked_visits,
                           sum(CASE WHEN alcohol_drug_indicator NOT IN ('None Reported','Not Recorded')
                                    THEN 1 ELSE 0 END) AS with_indicator
                    FROM linked GROUP BY 1)
        SELECT a.mechanism, a.ed_visits, lk.linked_visits, lk.with_indicator,
               lk.with_indicator::DOUBLE / lk.linked_visits AS share_of_linked_ems_visits,
               lk.with_indicator::DOUBLE / a.ed_visits AS share_of_all_ed_visits
        FROM all_ed a JOIN lk USING (mechanism) ORDER BY 1""").df()


def q2_outcomes(con) -> pd.DataFrame:
    # Arrival mode comes from the ED record itself (PV2-38 / modeOfArrival); linkage adds EMS
    # field-triage information, used here to stratify EMS arrivals.
    return con.execute("""
        WITH base AS (
          SELECT d.mechanism,
                 CASE WHEN d.arrival_mode = 'A' THEN 'EMS (ambulance)' ELSE 'Private / walk-in' END AS arrival,
                 CASE WHEN d.arrival_mode <> 'A' THEN 'n/a (no EMS record)'
                      WHEN l.ed_encounter_id IS NULL THEN 'EMS arrival, not linked'
                      WHEN l.trauma_high_risk <> 'None Reported' THEN 'EMS: high-risk triage criteria'
                      ELSE 'EMS: no high-risk criteria' END AS ems_triage,
                 d.disposition
          FROM ed_mech d LEFT JOIN linked l USING (ed_encounter_id))
        SELECT mechanism, arrival, ems_triage, count(*) AS n,
               avg(CASE WHEN disposition = 'admitted' THEN 1 ELSE 0 END) AS admitted,
               avg(CASE WHEN disposition = 'transferred' THEN 1 ELSE 0 END) AS transferred,
               avg(CASE WHEN disposition = 'died' THEN 1 ELSE 0 END) AS died,
               avg(CASE WHEN disposition = 'discharged' THEN 1 ELSE 0 END) AS discharged
        FROM base GROUP BY ALL ORDER BY 1, 2, 3""").df()


def q3_intervals(con) -> pd.DataFrame:
    return con.execute("""
        SELECT urbanicity, mechanism, count(*) AS n,
               quantile_cont(m, 0.25) AS p25_min, median(m) AS median_min,
               quantile_cont(m, 0.75) AS p75_min, quantile_cont(m, 0.90) AS p90_min
        FROM (SELECT urbanicity, mechanism,
                     date_diff('second', unit_notified_ts, arrival_ts) / 60.0 AS m FROM linked)
        GROUP BY ALL ORDER BY 1, 2""").df()


def q4_triage(con) -> pd.DataFrame:
    return con.execute("""
        SELECT CASE WHEN trauma_high_risk <> 'None Reported' THEN 'High-risk criteria documented'
                    ELSE 'No high-risk criteria' END AS field_triage,
               count(*) AS n,
               avg(CASE WHEN disposition IN ('admitted','transferred','died') THEN 1 ELSE 0 END)
                   AS admitted_transferred_or_died
        FROM linked GROUP BY 1 ORDER BY 1""").df()


QUESTIONS = {
    "q1_alcohol_drug": (
        "What share of ED visits for MVCs and falls had an EMS-documented alcohol/drug indicator (eHistory.17)?",
        q1_alcohol,
    ),
    "q2_outcomes_by_arrival": (
        "How do ED dispositions differ for EMS-transported vs privately arrived patients? (descriptive)",
        q2_outcomes,
    ),
    "q3_ems_to_ed_interval": (
        "How long from EMS unit notification (eTimes.03) to ED arrival, by urbanicity?",
        q3_intervals,
    ),
    "q4_field_triage": (
        "Among linked EMS patients, how often are those with/without high-risk field-triage criteria (eInjury.03) admitted, transferred or die?",
        q4_triage,
    ),
}


def run(cfg: dict) -> dict:
    paths = resolve_paths(cfg)
    out = {}
    for qid, (question, fn) in QUESTIONS.items():
        frames = []
        for src in LINK_SOURCES:
            con = _con(paths, src)
            df = fn(con)
            con.close()
            df.insert(0, "link_source", src)
            frames.append(df)
        out[qid] = {"question": question, "table": pd.concat(frames, ignore_index=True)}
    return out


def headline(out: dict) -> dict:
    q1 = out["q1_alcohol_drug"]["table"]
    q3 = out["q3_ems_to_ed_interval"]["table"]
    q4 = out["q4_field_triage"]["table"]
    h = {}
    for src in LINK_SOURCES:
        a = q1[q1.link_source == src]
        h[src] = {
            "alcohol_share_of_linked_mvc": float(
                a[a.mechanism == "MVC"].share_of_linked_ems_visits.iloc[0]
            ),
            "alcohol_share_of_linked_fall": float(
                a[a.mechanism == "Fall"].share_of_linked_ems_visits.iloc[0]
            ),
            "median_interval_min_rural": float(
                q3[(q3.link_source == src) & (q3.urbanicity == "rural")].median_min.median()
            ),
            "median_interval_min_urban": float(
                q3[(q3.link_source == src) & (q3.urbanicity == "urban")].median_min.median()
            ),
            "high_risk_triage_admit_transfer_or_died": float(
                q4[
                    (q4.link_source == src) & (q4.field_triage == "High-risk criteria documented")
                ].admitted_transferred_or_died.iloc[0]
            ),
            "high_risk_triage_n_linked": int(
                q4[
                    (q4.link_source == src) & (q4.field_triage == "High-risk criteria documented")
                ].n.iloc[0]
            ),
        }
    return h


def save(cfg: dict, out: dict) -> None:
    rd = resolve_paths(cfg)["results_dir"] / "analysis"
    for qid, v in out.items():
        sort = [c for c in v["table"].columns if v["table"][c].dtype == object]
        write_csv(v["table"], rd / f"{qid}.csv", sort)
    write_json(
        {
            "disclaimer": DISCLAIMER,
            "framing": "Demonstrations of what linkage makes possible — not findings.",
            "confounding_note": CONFOUNDING_NOTE,
            "link_sources": LINK_SOURCES,
            "questions": {k: v["question"] for k, v in out.items()},
            "headline": headline(out),
        },
        rd / "summary.json",
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = run(cfg)
    save(cfg, out)
    print(f"[analysis] {DISCLAIMER} Demonstrations, not findings.")
    for qid, v in out.items():
        print(f"\n== {qid}: {v['question']}")
        print(v["table"].to_string(index=False, max_rows=30))


if __name__ == "__main__":
    main()

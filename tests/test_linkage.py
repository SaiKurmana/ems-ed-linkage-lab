"""Linkage metrics, standardisation and Splink behaviour on the CI dataset."""

from __future__ import annotations

import pandas as pd

from common.io import read_json
from linkage.evaluate import metrics
from linkage.prep import clean_name, prep_ed
from linkage.probabilistic import one_to_one


def test_metrics_toy():
    truth = pd.DataFrame(
        {"ems_uuid": ["a", "b", "c", "d"], "ed_encounter_id": ["1", "2", "3", "4"]}
    )
    pred = pd.DataFrame({"ems_uuid": ["a", "b", "x"], "ed_encounter_id": ["1", "9", "3"]})
    m = metrics(pred, truth)
    assert (m["true_positives"], m["false_positives"], m["false_negatives"]) == (1, 2, 3)
    assert m["precision"] == 1 / 3 and m["recall"] == 0.25
    assert abs(m["false_match_rate"] - 2 / 3) < 1e-12


def test_one_to_one_is_greedy_and_unique():
    s = pd.DataFrame(
        {
            "ems_uuid": ["a", "a", "b"],
            "ed_encounter_id": ["1", "2", "1"],
            "match_probability": [0.99, 0.95, 0.97],
        }
    )
    out = one_to_one(s, 0.9)
    assert list(zip(out.ems_uuid, out.ed_encounter_id, strict=True)) == [("a", "1")]


def test_clean_name_and_alias_nulling():
    assert clean_name("José-Luis  O'Neil") == "JOSE LUIS O NEIL"
    ed = pd.DataFrame(
        {
            "ed_encounter_id": ["H1"],
            "first_name": ["ZULU"],
            "last_name": ["TRAUMA"],
            "dob": ["1900-01-01"],
            "sex": ["U"],
            "race": ["Unknown"],
            "ethnicity": ["Unknown"],
            "hospital_county": ["C01"],
            "arrival_ts": pd.to_datetime(["2024-01-01 10:00"]),
        }
    )
    p = prep_ed(ed).iloc[0]
    assert p.first_name is None and p.last_name is None and p.dob is None and p.sex is None


def test_splink_reasonable_and_worse_for_most_severe(pipeline):
    res = read_json(pipeline["paths"]["results_dir"] / "linkage_metrics.json")["methods"]
    assert res["splink_time"]["precision"] > 0.95
    assert res["splink_time"]["recall"] > 0.7
    assert res["hybrid_C"]["recall"] >= max(res["det_C"]["recall"], res["splink_time"]["recall"])
    sub = pd.read_csv(pipeline["paths"]["results_dir"] / "subgroup_recall.csv")
    sev = (
        sub[(sub.method == "splink_time") & (sub.dimension == "severity")].set_index("group").recall
    )
    assert sev["critical"] < sev["minor"]


def test_outputs_exist(pipeline):
    rd = pipeline["paths"]["results_dir"]
    for f in [
        "data_profile.json",
        "pattern_logs.json",
        "linkage_metrics.json",
        "subgroup_recall.csv",
        "threshold_sweep.csv",
        "latency.csv",
        "analysis/summary.json",
    ]:
        assert (rd / f).exists(), f

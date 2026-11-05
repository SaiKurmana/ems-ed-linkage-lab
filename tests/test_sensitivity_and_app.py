"""Sensitivity scenarios, latency sensitivity, and the Streamlit app smoke test."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from common.io import read_json

REPO = Path(__file__).resolve().parents[1]


def test_sensitivity_baseline_reproduces_main_results(pipeline):
    rd = pipeline["paths"]["results_dir"]
    main = read_json(rd / "linkage_metrics.json")["methods"]
    sens = read_json(rd / "sensitivity" / "summary.json")["scenarios"]["baseline"]["recall"]
    for m in ("det_A", "det_B", "det_C", "hybrid_C", "splink_time"):
        assert abs(sens[m]["all"] - main[m]["recall"]) < 1e-9, m


def test_rural_scenario_recall_tracks_stratum_carry_rates(pipeline):
    t = pd.read_csv(pipeline["paths"]["results_dir"] / "sensitivity" / "carry_by_urbanicity.csv")
    sc = t[t.scenario == "rural_small_agency_carry_gap"]
    for m in ("det_A", "det_C"):
        for urb in ("rural", "urban"):
            row = sc[(sc.method == m) & (sc.urbanicity == urb)].iloc[0]
            # exact counts per stratum and stage: only rounding (one record per stage) can move it
            assert abs(row.recall - row.expected_carry_rate) <= 3 / row.n_true_links + 1e-9, (
                m,
                urb,
            )
        rural = sc[(sc.method == m) & (sc.urbanicity == "rural")].recall.iloc[0]
        urban = sc[(sc.method == m) & (sc.urbanicity == "urban")].recall.iloc[0]
        assert urban - rural > 0.15
    hyb = sc[sc.method == "hybrid_C"].set_index("urbanicity").recall
    det = sc[sc.method == "det_C"].set_index("urbanicity").recall
    assert (hyb["urban"] - hyb["rural"]) < (det["urban"] - det["rural"])


def test_latency_sensitivity_is_monotone_in_lag(pipeline):
    s = pd.read_csv(pipeline["paths"]["results_dir"] / "latency_sensitivity_summary.csv")
    s = s[s.method == "splink_time"].sort_values("probabilistic_lag_months_after_year_end")
    assert list(s.probabilistic_lag_months_after_year_end) == [12, 18, 24, 36]
    assert s.share_available_at_24_months.is_monotonic_decreasing


def test_streamlit_app_runs_without_exceptions():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(REPO / "app" / "streamlit_app.py"), default_timeout=120).run()
    assert not at.exception, [e.message for e in at.exception]
    assert any("Synthetic data" in w.value for w in at.warning)

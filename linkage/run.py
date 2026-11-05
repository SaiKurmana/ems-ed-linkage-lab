"""Run and evaluate every linkage method against the ground truth.

Methods
  det_A / det_B / det_C   deterministic join on the UUID as each integration pattern left it
  splink_time             Splink with minute-level EMS→ED arrival-time comparison
  splink_date             Splink with arrival DATE only (typical of retrospective linkage)
  hybrid_C                UUID join (pattern C) first, Splink (time) on the remaining records

Writes results/linkage_metrics.json, subgroup_recall.csv, threshold_sweep.csv, latency.csv,
splink_model.json, runtime.json (machine-dependent) and data/linked/<method>.parquet.

Usage:  python -m linkage.run --config config/default.yaml
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from common import DISCLAIMER
from common.config import load_config, resolve_paths
from common.io import write_csv, write_json, write_parquet
from linkage import evaluate, prep, probabilistic
from linkage.deterministic import link_on_uuid

METHODS = {
    "det_A": ("Deterministic UUID — Pattern A (HL7 v2 point-to-point)", "deterministic"),
    "det_B": ("Deterministic UUID — Pattern B (HIE match + write-back)", "deterministic"),
    "det_C": ("Deterministic UUID — Pattern C (FHIR API identifier)", "deterministic"),
    "splink_time": (
        "Probabilistic — Splink, name/DOB/sex/race/county + arrival time",
        "probabilistic",
    ),
    "splink_date": (
        "Probabilistic — Splink, name/DOB/sex/race/county + arrival date only",
        "probabilistic",
    ),
    "hybrid_C": ("Hybrid — Pattern C UUID first, then Splink (time) on the rest", "hybrid"),
}


def latency_curve(
    pred: pd.DataFrame,
    truth: pd.DataFrame,
    gt: pd.DataFrame,
    method: str,
    cfg: dict,
    horizon_months: int = 48,
) -> pd.DataFrame:
    """Share of all true links that are correctly linked AND available for analysis, by months
    since the encounter. Lags are configurable ASSUMPTIONS (config: latency_assumptions)."""
    la = cfg["latency_assumptions"]
    year = int(cfg["synthetic_year"])
    t = truth.merge(gt[["ems_uuid", "event_ts"]], on="ems_uuid")
    found = set(zip(pred.ems_uuid, pred.ed_encounter_id, strict=True))
    ok = np.array([(a, b) in found for a, b in zip(t.ems_uuid, t.ed_encounter_id, strict=True)])
    if method.startswith("splink"):
        avail = pd.Timestamp(year + 1, 1, 1) + pd.DateOffset(
            months=la["probabilistic_months_after_year_end"]
        )
        lag_m = ((avail - t.event_ts).dt.days / 30.4375).to_numpy()
    elif method == "det_B":
        lag_m = np.full(len(t), la["hie_hours"] / 24 / 30.4375)
    else:
        lag_m = np.full(len(t), la["deterministic_days"] / 30.4375)
    rows = [
        {
            "method": method,
            "months_since_encounter": m,
            "share_of_true_links_available": float((ok & (lag_m <= m)).mean()),
        }
        for m in range(horizon_months + 1)
    ]
    return pd.DataFrame(rows)


def run(cfg: dict) -> dict:
    paths = resolve_paths(cfg)
    raw = paths["data_dir"] / "raw"
    ems = pd.read_parquet(raw / "ems_records.parquet")
    ed = pd.read_parquet(raw / "ed_encounters.parquet")
    truth = pd.read_parquet(raw / "truth_links.parquet")
    gt = pd.read_parquet(raw / "ground_truth.parquet")
    gt_ems = gt[gt.ems_uuid.notna()]

    preds, runtime, extra = {}, {}, {}
    for k in ("A", "B", "C"):
        ed_k = pd.read_parquet(paths["data_dir"] / "patterns" / f"ed_records_{k}.parquet")
        t0 = time.perf_counter()
        preds[f"det_{k}"] = link_on_uuid(ems, ed_k)
        runtime[f"det_{k}"] = time.perf_counter() - t0

    ems_p, ed_p = prep.prep_ems(ems), prep.prep_ed(ed)
    thr = cfg["linkage"]["splink"]["match_threshold"]
    sweep_rows = []
    for name, use_time in (("splink_time", True), ("splink_date", False)):
        t0 = time.perf_counter()
        scored, model = probabilistic.train_and_predict(ems_p, ed_p, cfg, use_time=use_time)
        preds[name] = probabilistic.one_to_one(scored, thr)
        runtime[name] = time.perf_counter() - t0
        extra[name] = {"scored": scored, "model": model}
        for th in cfg["linkage"]["splink"]["threshold_sweep"]:
            m = evaluate.metrics(probabilistic.one_to_one(scored, th), truth)
            sweep_rows.append(
                {
                    "method": name,
                    "threshold": th,
                    **{k: m[k] for k in ("precision", "recall", "f1")},
                }
            )

    # hybrid: UUID links from pattern C, then Splink on records not already linked
    t0 = time.perf_counter()
    det = preds["det_C"]
    rest = extra["splink_time"]["scored"]
    rest = rest[~rest.ems_uuid.isin(det.ems_uuid) & ~rest.ed_encounter_id.isin(det.ed_encounter_id)]
    preds["hybrid_C"] = pd.concat(
        [det, probabilistic.one_to_one(rest, thr)[["ems_uuid", "ed_encounter_id"]]],
        ignore_index=True,
    )
    runtime["hybrid_C"] = runtime["det_C"] + runtime["splink_time"] + (time.perf_counter() - t0)

    metrics, sub_frames, lat_frames = {}, [], []
    for name, pred in preds.items():
        m = evaluate.metrics(pred, truth)
        m.update(
            {
                "label": METHODS[name][0],
                "family": METHODS[name][1],
                "n_declared_links": int(len(pred)),
            }
        )
        metrics[name] = m
        s = evaluate.subgroup_recall(pred, truth, gt_ems)
        s.insert(0, "method", name)
        sub_frames.append(s)
        if name != "hybrid_C":  # hybrid mixes immediate (UUID) and batch (Splink) availability
            lat_frames.append(latency_curve(pred, truth, gt_ems, name, cfg))
        write_parquet(
            pred[["ems_uuid", "ed_encounter_id"]],
            paths["data_dir"] / "linked" / f"{name}.parquet",
            ["ems_uuid", "ed_encounter_id"],
        )

    # misses explained: why did Splink (time) miss true links?
    found = set(
        zip(preds["splink_time"].ems_uuid, preds["splink_time"].ed_encounter_id, strict=True)
    )
    tt = truth.merge(gt_ems[["ems_uuid", "ems_dq_flags", "ed_dq_flags"]], on="ems_uuid")
    tt["missed"] = [
        (a, b) not in found for a, b in zip(tt.ems_uuid, tt.ed_encounter_id, strict=True)
    ]
    miss_reasons = {}
    for flag in (
        "unidentified",
        "trauma_alias",
        "name_variant",
        "name_typo",
        "dob_error",
        "dob_missing",
        "race_misclass",
    ):
        has = tt.ems_dq_flags.fillna("").str.contains(flag) | tt.ed_dq_flags.fillna(
            ""
        ).str.contains(flag)
        miss_reasons[flag] = {
            "n_true_links_with_issue": int(has.sum()),
            "splink_time_recall_when_present": float(1 - tt.missed[has].mean())
            if has.any()
            else None,
        }
    clean = ~(tt.ems_dq_flags.fillna("").astype(bool) | tt.ed_dq_flags.fillna("").astype(bool))
    miss_reasons["no_issue"] = {
        "n_true_links_with_issue": int(clean.sum()),
        "splink_time_recall_when_present": float(1 - tt.missed[clean].mean()),
    }

    return {
        "metrics": metrics,
        "subgroups": pd.concat(sub_frames, ignore_index=True),
        "sweep": pd.DataFrame(sweep_rows),
        "latency": pd.concat(lat_frames, ignore_index=True),
        "runtime": runtime,
        "models": {k: v["model"] for k, v in extra.items()},
        "miss_reasons": miss_reasons,
        "n_true_links": int(len(truth)),
    }


def save(cfg: dict, out: dict) -> None:
    paths = resolve_paths(cfg)
    rd = paths["results_dir"]
    write_json(
        {
            "disclaimer": DISCLAIMER,
            "n_true_links": out["n_true_links"],
            "match_threshold": cfg["linkage"]["splink"]["match_threshold"],
            "definitions": {
                "precision": "TP / (TP + FP)",
                "recall": "TP / (TP + FN)",
                "false_match_rate": "FP / (TP + FP): share of declared links that are wrong",
                "missed_link_rate": "FN / (TP + FN)",
            },
            "methods": out["metrics"],
            "splink_time_recall_by_data_quality_issue": out["miss_reasons"],
        },
        rd / "linkage_metrics.json",
    )
    write_csv(out["subgroups"], rd / "subgroup_recall.csv", ["method", "dimension", "group"])
    write_csv(out["sweep"], rd / "threshold_sweep.csv", ["method", "threshold"])
    write_csv(out["latency"], rd / "latency.csv", ["method", "months_since_encounter"])
    write_json({"disclaimer": DISCLAIMER, **out["models"]}, rd / "splink_model.json")
    write_json(
        {
            "disclaimer": DISCLAIMER,
            "note": "Wall-clock seconds on the machine that last ran `make link`; varies by machine.",
            "seconds": {k: round(v, 2) for k, v in out["runtime"].items()},
        },
        rd / "runtime.json",
    )


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    out = run(cfg)
    save(cfg, out)
    print(f"[linkage] {DISCLAIMER}  true links = {out['n_true_links']}")
    print(f"  {'method':<12} {'precision':>9} {'recall':>7} {'F1':>6} {'FMR':>6} {'sec':>6}")
    for k, m in out["metrics"].items():
        print(
            f"  {k:<12} {m['precision']:>9.3f} {m['recall']:>7.3f} {m['f1']:>6.3f} "
            f"{m['false_match_rate']:>6.3f} {out['runtime'][k]:>6.2f}"
        )


if __name__ == "__main__":
    main()

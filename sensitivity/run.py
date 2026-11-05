"""Named sensitivity scenarios for UUID carry (synthetic data — for demonstration only).

The MAIN results assume carry failures are random with respect to patients and agencies
("baseline"). Each scenario in `config: sensitivity.scenarios` overrides pattern pass rates
(e.g. lower rates for rural / small agencies — an ASSUMPTION). For the baseline and every
scenario this re-runs patterns A, B and C, the deterministic UUID joins and the hybrid
(UUID first, then the already-trained Splink scores), and reports recall by urbanicity.

Requires `make data simulate link` first (uses Splink scored pairs from data/linked/).

Writes results/sensitivity/carry_by_urbanicity.csv and results/sensitivity/summary.json.
Usage:  python -m sensitivity.run --config config/default.yaml
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from common import DISCLAIMER
from common.config import deep_merge, load_config, resolve_paths
from common.io import write_csv, write_json
from linkage.deterministic import link_on_uuid
from linkage.probabilistic import one_to_one
from patterns import pattern_a, pattern_b, pattern_c
from patterns.common import expected_carry_rate, stratum_rate

PATTERNS = {
    "A": (pattern_a, "A_point_to_point"),
    "B": (pattern_b, "B_hie"),
    "C": (pattern_c, "C_fhir_api"),
}
STAGES = {"A": pattern_a.STAGES, "C": pattern_c.STAGES}
BASELINE = {
    "label": "Baseline (main result): carry failures random with respect to patient and agency",
    "assumption": "Same pass rates for every agency (config: patterns.*).",
    "overrides": {},
}


def _recall_by_urbanicity(pred: pd.DataFrame, truth: pd.DataFrame, gt: pd.DataFrame) -> list[dict]:
    found = set(zip(pred.ems_uuid, pred.ed_encounter_id, strict=True))
    t = truth.merge(gt[["ems_uuid", "urbanicity"]], on="ems_uuid", how="left")
    t["linked"] = [(a, b) in found for a, b in zip(t.ems_uuid, t.ed_encounter_id, strict=True)]
    rows = [{"urbanicity": "all", "n_true_links": len(t), "recall": float(t.linked.mean())}]
    for u, sub in t.groupby("urbanicity"):
        rows.append({"urbanicity": u, "n_true_links": len(sub), "recall": float(sub.linked.mean())})
    return rows


def run(cfg: dict) -> dict:
    paths = resolve_paths(cfg)
    raw = paths["data_dir"] / "raw"
    ems = pd.read_parquet(raw / "ems_records.parquet")
    ed = pd.read_parquet(raw / "ed_encounters.parquet")
    truth = pd.read_parquet(raw / "truth_links.parquet")
    gt = pd.read_parquet(raw / "ground_truth.parquet")
    gt = gt[gt.ems_uuid.notna()]
    scored = pd.read_parquet(paths["data_dir"] / "linked" / "splink_time_scored.parquet")
    scored = scored.sort_values(
        ["match_probability", "ems_uuid", "ed_encounter_id"],
        ascending=[False, True, True],
        kind="mergesort",
    )
    thr = cfg["linkage"]["splink"]["match_threshold"]
    splink_pred = one_to_one(scored, thr)

    scenarios = {"baseline": BASELINE, **cfg.get("sensitivity", {}).get("scenarios", {})}
    rows, summary = [], {}
    seed = int(cfg["seed"])
    for name, sc in scenarios.items():
        scfg = deep_merge(cfg, sc.get("overrides", {}))
        preds = {}
        for i, (k, (mod, _key)) in enumerate(PATTERNS.items()):
            rng = np.random.default_rng(seed + 101 * (i + 1))  # same streams as patterns.simulate
            kwargs = {"validate_all": False} if k == "C" else {}
            res = mod.run(ems, ed, truth, scfg, rng, **kwargs)
            preds[f"det_{k}"] = link_on_uuid(ems, res["ed_records"])
        det = preds["det_C"]
        rest = scored[
            ~scored.ems_uuid.isin(det.ems_uuid) & ~scored.ed_encounter_id.isin(det.ed_encounter_id)
        ]
        preds["hybrid_C"] = pd.concat(
            [det, one_to_one(rest, thr)[["ems_uuid", "ed_encounter_id"]]], ignore_index=True
        )
        preds["splink_time"] = splink_pred  # unaffected by carry failures; shown for reference

        expected = {}
        for k, st in STAGES.items():
            pc = scfg["patterns"][PATTERNS[k][1]]
            expected[f"det_{k}"] = {
                u: expected_carry_rate([stratum_rate(pc, u, s) for s in st])
                for u in ("rural", "urban")
            }
        gaps = {}
        for method, pred in preds.items():
            r = _recall_by_urbanicity(pred, truth, gt)
            for row in r:
                exp = expected.get(method, {}).get(row["urbanicity"])
                rows.append({"scenario": name, "method": method, **row, "expected_carry_rate": exp})
            by = {x["urbanicity"]: x["recall"] for x in r}
            gaps[method] = {
                "urban": by["urban"],
                "rural": by["rural"],
                "all": by["all"],
                "urban_minus_rural_pp": round(100 * (by["urban"] - by["rural"]), 2),
            }
        summary[name] = {
            "label": sc["label"],
            "assumption": " ".join(str(sc["assumption"]).split()),
            "overrides": sc.get("overrides", {}),
            "recall": gaps,
        }
    return {"table": pd.DataFrame(rows), "summary": summary}


def save(cfg: dict, out: dict) -> None:
    rd = resolve_paths(cfg)["results_dir"] / "sensitivity"
    write_csv(out["table"], rd / "carry_by_urbanicity.csv", ["scenario", "method", "urbanicity"])
    write_json(
        {
            "disclaimer": DISCLAIMER,
            "note": "Baseline is the main result. Scenarios are illustrative ASSUMPTIONS.",
            "scenarios": out["summary"],
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
    print(f"[sensitivity] {DISCLAIMER}")
    for name, s in out["summary"].items():
        print(f"  {name}")
        for m, g in s["recall"].items():
            print(
                f"    {m:<12} urban {g['urban']:.3f}  rural {g['rural']:.3f}  gap {g['urban_minus_rural_pp']:+.1f} pp"
            )


if __name__ == "__main__":
    main()

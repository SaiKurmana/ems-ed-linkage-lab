"""Markdown rows rendered from committed results (used by README, site and a sync test)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from common.charts import METHOD_SHORT

REPO = Path(__file__).resolve().parents[1]
RD = REPO / "results"
SENS_METHODS = ["hybrid_C", "det_A", "det_B", "det_C", "splink_time"]
MILESTONES = [6, 12, 18, 24, 36, 48]


def sensitivity_records() -> list[dict]:
    s = json.loads((RD / "sensitivity" / "summary.json").read_text())["scenarios"]
    base, sc = s["baseline"]["recall"], s["rural_small_agency_carry_gap"]["recall"]
    return [
        {
            "method": METHOD_SHORT[m],
            "base_urban": base[m]["urban"],
            "base_rural": base[m]["rural"],
            "sc_urban": sc[m]["urban"],
            "sc_rural": sc[m]["rural"],
            "sc_gap_pp": sc[m]["urban_minus_rural_pp"],
        }
        for m in SENS_METHODS
    ]


def sensitivity_rows() -> str:
    return "\n".join(
        f"| {r['method']} | {r['base_urban']:.3f} | {r['base_rural']:.3f} | {r['sc_urban']:.3f} | "
        f"{r['sc_rural']:.3f} | {r['sc_gap_pp']:+.1f} |"
        for r in sensitivity_records()
    )


def latency_records() -> list[dict]:
    d = pd.read_csv(RD / "latency_sensitivity_summary.csv")
    cfg = yaml.safe_load((REPO / "config" / "default.yaml").read_text())
    default = cfg["latency_assumptions"]["probabilistic_months_after_year_end"]
    out = []
    for r in d.itertuples(index=False):
        if r.method == "det_C":
            label = "UUID · Pattern C (at the encounter)"
        else:
            lag = int(r.probabilistic_lag_months_after_year_end)
            label = f"Splink, batch {lag} mo after year end" + (
                " (default)" if lag == default else ""
            )
        out.append(
            {
                "label": label,
                **{m: getattr(r, f"share_available_at_{m}_months") for m in MILESTONES},
            }
        )
    return out


def latency_rows() -> str:
    return "\n".join(
        f"| {r['label']} | " + " | ".join(f"{r[m]:.1%}" for m in MILESTONES) + " |"
        for r in latency_records()
    )


if __name__ == "__main__":
    print(sensitivity_rows())
    print()
    print(latency_rows())

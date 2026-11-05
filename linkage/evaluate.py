"""Evaluation of predicted EMS–ED links against the separately held ground truth."""

from __future__ import annotations

import pandas as pd


def _pairs(df: pd.DataFrame) -> set[tuple[str, str]]:
    return set(zip(df.ems_uuid, df.ed_encounter_id, strict=True))


def metrics(pred: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """precision, recall, F1 and false-match rate.

    false_match_rate = FP / (TP + FP): the share of declared links that join two different
    people's encounters (equivalently 1 - precision). missed_link_rate = FN / (TP + FN).
    """
    p, t = _pairs(pred), _pairs(truth)
    tp, fp, fn = len(p & t), len(p - t), len(t - p)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "false_match_rate": fp / (tp + fp) if tp + fp else 0.0,
        "missed_link_rate": fn / (tp + fn) if tp + fn else 0.0,
    }


def subgroup_recall(
    pred: pd.DataFrame,
    truth: pd.DataFrame,
    gt: pd.DataFrame,
    dims=("race_eth", "age_group", "urbanicity", "severity"),
) -> pd.DataFrame:
    """Recall within subgroups defined by TRUE (latent) attributes from the ground truth."""
    found = _pairs(pred)
    t = truth.merge(gt[["ems_uuid", *dims]], on="ems_uuid", how="left")
    t["linked"] = [(a, b) in found for a, b in zip(t.ems_uuid, t.ed_encounter_id, strict=True)]
    rows = []
    for d in dims:
        for g, sub in t.groupby(d):
            rows.append(
                {
                    "dimension": d,
                    "group": str(g),
                    "n_true_links": int(len(sub)),
                    "recall": float(sub.linked.mean()),
                }
            )
    return pd.DataFrame(rows)

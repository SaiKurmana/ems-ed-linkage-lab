"""Probabilistic linkage with Splink (Fellegi–Sunter model on DuckDB).

Comparisons: first name, last name, DOB, sex, race/ethnicity, county and either the time
difference between EMS arrival at destination and ED arrival (minutes), or — in the
"date-only" variant typical of retrospective statewide linkage — an exact arrival-date match. Blocking (OR-ed rules):
county + arrival date, DOB, and last-name prefix + arrival date.
"""

from __future__ import annotations

import logging

import pandas as pd
import splink.comparison_library as cl
from splink import Linker, SettingsCreator, block_on
from splink.backends.duckdb import DuckDBAPI

logging.getLogger("splink").setLevel(logging.ERROR)


def settings(use_time: bool = True) -> SettingsCreator:
    time_comparison = (
        cl.AbsoluteTimeDifferenceAtThresholds(
            "ts",
            input_is_string=False,
            metrics=["minute", "minute", "minute"],
            thresholds=[20, 60, 240],
        )
        if use_time
        else cl.ExactMatch("arrival_date")
    )
    return SettingsCreator(
        link_type="link_only",
        unique_id_column_name="unique_id",
        blocking_rules_to_generate_predictions=[
            block_on("county", "arrival_date"),
            block_on("dob"),
            block_on("substr(last_name, 1, 3)", "arrival_date"),
        ],
        comparisons=[
            cl.NameComparison("first_name"),
            cl.NameComparison("last_name"),
            cl.DateOfBirthComparison("dob", input_is_string=True),
            cl.ExactMatch("sex"),
            cl.ExactMatch("race_eth"),
            cl.ExactMatch("county"),
            time_comparison,
        ],
        retain_intermediate_calculation_columns=False,
        retain_matching_columns=False,
    )


def train_and_predict(
    ems_prep: pd.DataFrame,
    ed_prep: pd.DataFrame,
    cfg: dict,
    use_time: bool = True,
    min_probability: float = 0.3,
) -> tuple[pd.DataFrame, dict]:
    """Return scored candidate pairs (ems_uuid, ed_encounter_id, match_probability, match_weight)."""
    sp = cfg["linkage"]["splink"]
    db = DuckDBAPI()
    ems_sdf = db.register(ems_prep, table_name="ems_prep")
    ed_sdf = db.register(ed_prep, table_name="ed_prep")
    linker = Linker([ems_sdf, ed_sdf], settings(use_time), log_level=logging.ERROR)

    linker.training.estimate_probability_two_random_records_match(
        [block_on("first_name", "last_name", "dob"), block_on("dob", "county", "arrival_date")],
        recall=0.7,
    )
    linker.training.estimate_u_using_random_sampling(
        max_pairs=sp["u_max_pairs"], seed=int(cfg["seed"])
    )
    for rule in sp["em_blocking"]:
        linker.training.estimate_parameters_using_expectation_maximisation(
            block_on(*rule), record_sample_proportion=1.0
        )

    pred = linker.inference.predict(
        threshold_match_probability=min_probability
    ).as_pandas_dataframe()
    # orient pairs as (EMS, ED) — EMS uuids contain hyphens, ED encounter ids do not
    left_is_ems = pred.unique_id_l.str.contains("-")
    out = pd.DataFrame(
        {
            "ems_uuid": pred.unique_id_l.where(left_is_ems, pred.unique_id_r),
            "ed_encounter_id": pred.unique_id_r.where(left_is_ems, pred.unique_id_l),
            "match_probability": pred.match_probability.astype(float),
            "match_weight": pred.match_weight.astype(float),
        }
    )
    out = out.sort_values(
        ["match_probability", "ems_uuid", "ed_encounter_id"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    model = {
        "probability_two_random_records_match": float(
            linker._settings_obj._probability_two_random_records_match
        ),
        "comparisons": _match_weights(linker),
    }
    return out, model


def _match_weights(linker) -> list[dict]:
    rows = []
    for c in linker._settings_obj.comparisons:
        for lvl in c.comparison_levels:
            if lvl.is_null_level:
                continue
            rows.append(
                {
                    "comparison": c.output_column_name,
                    "level": lvl.label_for_charts,
                    "m": _f(lvl.m_probability),
                    "u": _f(lvl.u_probability),
                    "bayes_factor": _f(lvl._bayes_factor),
                }
            )
    return rows


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def one_to_one(scored: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Greedy one-to-one assignment: highest-probability pairs first, each record used once."""
    used_e, used_d, keep = set(), set(), []
    for e, d, p in zip(
        scored.ems_uuid, scored.ed_encounter_id, scored.match_probability, strict=True
    ):
        if p < threshold:
            break
        if e in used_e or d in used_d:
            continue
        used_e.add(e)
        used_d.add(d)
        keep.append((e, d, p))
    return pd.DataFrame(keep, columns=["ems_uuid", "ed_encounter_id", "match_probability"])

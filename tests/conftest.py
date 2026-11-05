"""Shared fixtures: run the small CI pipeline once per test session into a temp directory."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from common.config import load_config, resolve_paths
from pipeline import run_all

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def pipeline(tmp_path_factory):
    work = tmp_path_factory.mktemp("pipeline")
    cfg = run_all(REPO / "config" / "ci.yaml", work)
    paths = resolve_paths(cfg)
    raw = paths["data_dir"] / "raw"
    return {
        "cfg": cfg,
        "paths": paths,
        "ems": pd.read_parquet(raw / "ems_records.parquet"),
        "ed": pd.read_parquet(raw / "ed_encounters.parquet"),
        "truth": pd.read_parquet(raw / "truth_links.parquet"),
        "gt": pd.read_parquet(raw / "ground_truth.parquet"),
    }


@pytest.fixture(scope="session")
def ci_config():
    return load_config(REPO / "config" / "ci.yaml")

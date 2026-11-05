"""Deterministic I/O helpers: sorted exports, stable JSON."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from common import DISCLAIMER


def write_parquet(df: pd.DataFrame, path: Path, sort_by: list[str] | str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(sort_by, kind="mergesort").reset_index(drop=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    meta = {**(table.schema.metadata or {}), b"disclaimer": DISCLAIMER.encode("utf-8")}
    pq.write_table(table.replace_schema_metadata(meta), path)
    return path


def write_csv(df: pd.DataFrame, path: Path, sort_by: list[str] | str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if sort_by:
        df = df.sort_values(sort_by, kind="mergesort")
    df = df.copy()
    df.insert(0, "data_label", DISCLAIMER)  # every exported dataset is self-labelled
    df.to_csv(path, index=False, lineterminator="\n", float_format="%.6g")
    return path


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 6)
    if hasattr(obj, "item"):  # numpy scalar
        return _clean(obj.item())
    return obj


def write_json(obj, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(_clean(obj), fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    return path


def read_json(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

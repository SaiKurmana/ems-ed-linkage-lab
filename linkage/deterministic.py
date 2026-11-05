"""Deterministic linkage: an exact join on the EMS UUID carried into the ED record (DuckDB)."""

from __future__ import annotations

import duckdb
import pandas as pd


def link_on_uuid(ems: pd.DataFrame, ed_records: pd.DataFrame) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("ems", ems[["ems_uuid"]])
    con.register("ed", ed_records[["ed_encounter_id", "ems_uuid"]])
    pairs = con.execute(
        """
        SELECT e.ems_uuid, d.ed_encounter_id
        FROM ed d
        JOIN ems e ON d.ems_uuid = e.ems_uuid
        WHERE d.ems_uuid IS NOT NULL
        ORDER BY e.ems_uuid, d.ed_encounter_id
        """
    ).df()
    con.close()
    return pairs

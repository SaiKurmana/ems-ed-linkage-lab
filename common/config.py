"""Configuration loading with simple `extends:` inheritance."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "default.yaml"


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict[str, Any]:
    path = Path(path) if path else DEFAULT_CONFIG
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    parent = cfg.pop("extends", None)
    if parent:
        cfg = deep_merge(load_config(path.parent / parent), cfg)
    if overrides:
        cfg = deep_merge(cfg, overrides)
    return cfg


def resolve_paths(cfg: dict) -> dict[str, Path]:
    """Return absolute data/results/examples directories (relative paths are repo-relative)."""
    out = {}
    for key in ("data_dir", "results_dir", "examples_dir"):
        p = Path(cfg["paths"][key])
        out[key] = p if p.is_absolute() else REPO_ROOT / p
        out[key].mkdir(parents=True, exist_ok=True)
    return out

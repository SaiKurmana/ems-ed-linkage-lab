"""Run the whole pipeline (data -> simulate -> link -> analyze) into an isolated work directory.

Used by CI and tests:  python -m pipeline --config config/ci.yaml --workdir .ci_run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from analysis import run as analysis_run
from common.config import load_config
from linkage import run as linkage_run
from patterns import simulate
from synth import generate


def run_all(config: str | None, workdir: str | Path, validate_all_fhir: bool = True) -> dict:
    workdir = Path(workdir).resolve()
    cfg = load_config(
        config,
        overrides={
            "paths": {
                "data_dir": str(workdir / "data"),
                "results_dir": str(workdir / "results"),
                "examples_dir": str(workdir / "examples"),
            }
        },
    )
    generate.save(generate.generate(cfg), cfg)
    simulate.save(cfg, simulate.simulate(cfg, validate_all_fhir=validate_all_fhir))
    linkage_run.save(cfg, linkage_run.run(cfg))
    analysis_run.save(cfg, analysis_run.run(cfg))
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/ci.yaml")
    ap.add_argument("--workdir", default=".ci_run")
    args = ap.parse_args(argv)
    cfg = run_all(args.config, args.workdir)
    print(f"[pipeline] complete -> {cfg['paths']['results_dir']}")


if __name__ == "__main__":
    main()

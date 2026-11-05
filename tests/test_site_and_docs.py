"""Site build, required disclaimers, README numbers in sync with committed results."""

from __future__ import annotations

import json
from pathlib import Path

from common import AFFILIATION, DISCLAIMER
from site_src.build import DOCS, build

REPO = Path(__file__).resolve().parents[1]


def test_site_builds_with_disclaimers(tmp_path):
    out = build(tmp_path / "_site")
    pages = list(out.rglob("*.html"))
    assert (out / "index.html").exists() and len(pages) >= len(DOCS) + 3
    for p in pages:
        text = p.read_text(encoding="utf-8")
        assert DISCLAIMER in text, p
        assert "Not affiliated with, endorsed by, or produced for the CDC" in text, p
    assert (out / "examples" / "pattern_c").is_dir()


def test_readme_has_required_statements():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert AFFILIATION.replace("\n", " ") in " ".join(readme.split())
    assert "Sai Kurmana, MPH, MS, CPHIMS" in readme


def test_readme_headline_table_matches_committed_results():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    metrics = json.loads((REPO / "results" / "linkage_metrics.json").read_text())["methods"]
    for m in metrics.values():
        row = f"| {m['label']} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['false_match_rate']:.3f} |"
        assert row in readme, row


def test_standards_references_present():
    refs = (REPO / "docs" / "standards_references.md").read_text(encoding="utf-8")
    for needle in [
        "nemsis.org",
        "hl7.org/fhir/R4",
        "build.fhir.org",
        "terminology.hl7.org",
        "cms.gov",
        "Access date",
        "PV1-50",
        "Encounter",
    ]:
        assert needle in refs, needle


def test_every_doc_labels_synthetic():
    for key, _ in DOCS:
        assert DISCLAIMER in (REPO / "docs" / f"{key}.md").read_text(encoding="utf-8"), key


def test_readme_sensitivity_and_latency_tables_match_results():
    from site_src.tables import latency_rows, sensitivity_rows

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert sensitivity_rows() in readme
    assert latency_rows() in readme


def test_pydantic_pinned_below_2_for_fhir_resources():
    import re

    import pydantic

    req = (REPO / "requirements.txt").read_text(encoding="utf-8")
    pin = re.search(r"^pydantic==(\d+)\.", req, flags=re.M)
    assert pin and int(pin.group(1)) < 2
    assert re.search(r"^fhir\.resources==6\.1\.0$", req, flags=re.M)
    assert pydantic.VERSION.startswith("1.")

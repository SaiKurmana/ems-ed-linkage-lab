"""Build the static GitHub Pages site into _site/ from committed results, docs and examples.

Usage:  python -m site_src.build [--out _site]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from pathlib import Path

import markdown
import pandas as pd
import plotly.io as pio
import yaml
from plotly.offline import get_plotlyjs

from common import AFFILIATION, DISCLAIMER, EMS_UUID_SYSTEM, charts

REPO = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
DOCS = [
    ("architecture", "Architecture & data flows"),
    ("implementation_guide", "Implementation guide"),
    ("facilitators_and_barriers", "Facilitators & barriers"),
    ("partner_map", "Partner map"),
    ("privacy_and_security", "Privacy & security"),
    ("limitations", "Limitations"),
    ("standards_references", "Standards references"),
]


def esc(s) -> str:
    return html.escape(str(s), quote=True)


# ----------------------------------------------------------------------------- page shell
def page(
    title: str, body: str, root: str, cfg: dict, description: str, extra_head: str = ""
) -> str:
    nav = "".join(
        f'<a class="link" href="{root}{href}">{esc(label)}</a>'
        for href, label in [
            ("index.html#patterns", "Patterns"),
            ("index.html#results", "Results"),
            ("docs/index.html", "Docs"),
            ("examples/index.html", "Examples"),
        ]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%231c5cab'/%3E%3Cpath d='M13 7h6v6h6v6h-6v6h-6v-6H7v-6h6z' fill='white'/%3E%3C/svg%3E">
<link rel="stylesheet" href="{root}assets/style.css">
<script src="{root}assets/site.js"></script>
{extra_head}
</head>
<body>
<div class="banner" role="note">{esc(DISCLAIMER)} No real patients, agencies or hospitals.</div>
<header class="site"><div class="wrap nav">
  <a class="brand" href="{root}index.html">{esc(cfg["site_title"])}</a>{nav}
  <button class="theme-btn" id="theme-btn" type="button" aria-label="Toggle color theme">Dark mode</button>
</div></header>
<main class="wrap">
{body}
</main>
<footer class="site"><div class="wrap">
  <p><strong>{esc(DISCLAIMER)}</strong></p>
  <p>{esc(AFFILIATION)}</p>
  <p>Author: {esc(cfg["author"])} · <a href="{esc(cfg["repo_url"])}">Source on GitHub</a> ·
     <a href="{root}docs/standards_references.html">Standards references</a></p>
</div></footer>
</body>
</html>
"""


# ----------------------------------------------------------------------------- diagram
def patterns_svg() -> str:
    """Inline SVG of the three data flows; colours come from CSS variables (light/dark)."""

    def box(x, y, w, h, title, sub="", accent=False):
        stroke = "var(--accent)" if accent else "var(--border)"
        sw = 2 if accent else 1.5
        t = f'<text x="{x + w / 2}" y="{y + (h / 2 - 4 if sub else h / 2 + 5)}" text-anchor="middle" font-weight="600" font-size="14" fill="var(--text)">{esc(title)}</text>'
        s = (
            f'<text x="{x + w / 2}" y="{y + h / 2 + 14}" text-anchor="middle" font-size="11.5" fill="var(--text-2)">{esc(sub)}</text>'
            if sub
            else ""
        )
        return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="var(--surface)" stroke="{stroke}" stroke-width="{sw}"/>{t}{s}'

    def arrow(x1, y1, x2, y2, label="", dy=-7):
        mid = (
            f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 + dy}" text-anchor="middle" font-size="11.5" fill="var(--text-2)">{esc(label)}</text>'
            if label
            else ""
        )
        return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="var(--muted)" stroke-width="1.6" marker-end="url(#ah)"/>{mid}'

    def lane(y, tag, color, name):
        return (
            f'<rect x="8" y="{y}" width="1004" height="118" rx="12" fill="var(--surface-2)" stroke="none"/>'
            f'<rect x="8" y="{y}" width="6" height="118" rx="3" fill="{color}"/>'
            f'<text x="28" y="{y + 24}" font-size="13" font-weight="700" fill="var(--text)">{esc(tag)}</text>'
            f'<text x="28" y="{y + 42}" font-size="12" fill="var(--text-2)">{esc(name)}</text>'
        )

    parts = [
        '<svg viewBox="0 0 1020 420" role="img" aria-labelledby="dtitle ddesc" xmlns="http://www.w3.org/2000/svg">',
        '<title id="dtitle">Three ways the EMS UUID can reach the ED record</title>',
        '<desc id="ddesc">Pattern A: the ePCR sends an HL7 v2 ADT^A05 to the hospital, the UUID lands in PV1-50. '
        "Pattern B: EMS and ED both send ADT^A04 to an HIE which matches them and writes the UUID back with ADT^A08. "
        "Pattern C: an integration service PUTs the ED Encounter on a FHIR R4 API with an extra Encounter.identifier.</desc>",
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z" fill="var(--muted)"/></marker></defs>',
    ]
    # lane A
    y = 6
    parts += [
        lane(y, "A", "var(--s1)", "Point-to-point HL7 v2"),
        box(190, y + 30, 170, 58, "EMS ePCR", "UUID4 per report"),
        arrow(360, y + 59, 510, y + 59, "ADT^A05 (pre-admit)"),
        box(510, y + 30, 180, 58, "Interface engine", "parse + hold"),
        arrow(690, y + 59, 790, y + 59, "merge"),
        box(790, y + 30, 200, 58, "ED record", "PV1-50 = UUID", accent=True),
    ]
    # lane B
    y = 148
    parts += [
        lane(y, "B", "var(--s2)", "HIE intermediary"),
        box(190, y + 30, 170, 58, "EMS ePCR", "ADT^A04 → HIE"),
        arrow(360, y + 59, 500, y + 59, "UUID in PV1-19"),
        box(500, y + 22, 200, 74, "HIE matcher", "demographics + time"),
        arrow(700, y + 47, 790, y + 47, "ADT^A08", dy=-6),
        arrow(790, y + 75, 700, y + 75, "ED ADT^A04", dy=16),
        box(790, y + 30, 200, 58, "ED record", "PV1-50 = UUID", accent=True),
    ]
    # lane C
    y = 290
    parts += [
        lane(y, "C", "var(--s3)", "FHIR R4 API"),
        box(190, y + 30, 170, 58, "EMS ePCR", "at transfer of care"),
        arrow(360, y + 59, 510, y + 59, "UUID"),
        box(510, y + 30, 180, 58, "Integration svc", "transaction Bundle"),
        arrow(690, y + 59, 790, y + 59, "PUT Encounter"),
        box(790, y + 30, 200, 58, "ED Encounter", ".identifier = UUID", accent=True),
    ]
    parts.append("</svg>")
    return "".join(parts)


# ----------------------------------------------------------------------------- helpers
def fig_html(fig, div_id: str) -> str:
    return (
        '<div class="chart">'
        + pio.to_html(
            fig,
            include_plotlyjs=False,
            full_html=False,
            div_id=div_id,
            config={"displayModeBar": False, "responsive": True},
        )
        + "</div>"
    )


def results_table(metrics: dict) -> str:
    rows = []
    for k in charts.METHOD_SHORT:
        if k not in metrics:
            continue
        m = metrics[k]
        rows.append(
            f'<tr><td><span class="swatch" style="background:{charts.METHOD_COLOR[k]}"></span>{esc(m["label"])}</td>'
            f'<td class="num">{m["precision"]:.3f}</td><td class="num">{m["recall"]:.3f}</td>'
            f'<td class="num">{m["f1"]:.3f}</td><td class="num">{m["false_match_rate"]:.3f}</td></tr>'
        )
    return (
        '<div class="table-wrap"><table><caption class="sr-only">Linkage results (synthetic)</caption>'
        '<thead><tr><th>Method</th><th class="num">Precision</th><th class="num">Recall</th>'
        '<th class="num">F1</th><th class="num">False-match rate</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render_markdown(text: str, cfg: dict) -> str:
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<pre class="mermaid">{m.group(1)}</pre>',
        body,
        flags=re.S,
    )
    body = re.sub(r"<table>", '<div class="table-wrap"><table>', body)
    body = re.sub(r"</table>", "</table></div>", body)

    def fix_href(m):
        href = m.group(1)
        if href.startswith(("http", "#", "mailto:")):
            return m.group(0)
        if href.endswith(".md") or ".md#" in href:
            name = href.split("/")[-1].replace(".md", ".html")
            if href.startswith("../README"):
                return f'href="{cfg["repo_url"]}#readme"'
            return f'href="{name}"'
        if href.startswith("../examples/"):
            return f'href="../{href[3:]}"'
        if href.startswith("../"):
            return f'href="{cfg["repo_url"]}/blob/main/{href[3:]}"'
        return m.group(0)

    return re.sub(r'href="([^"]+)"', fix_href, body)


MERMAID_HEAD = """<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs";
const sources = [];
document.querySelectorAll("pre.mermaid").forEach((el, i) => { sources[i] = el.textContent; });
async function render() {
  const t = document.documentElement.getAttribute("data-theme");
  const dark = t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict" });
  const els = document.querySelectorAll("pre.mermaid");
  els.forEach((el, i) => { el.removeAttribute("data-processed"); el.textContent = sources[i]; });
  await mermaid.run({ nodes: els });
}
window.__renderMermaid = render;
render();
</script>"""


# ----------------------------------------------------------------------------- pages
def build_index(cfg: dict, out: Path) -> None:
    rd = REPO / "results"
    lm = json.loads((rd / "linkage_metrics.json").read_text())
    prof = json.loads((rd / "data_profile.json").read_text())
    plog = json.loads((rd / "pattern_logs.json").read_text())["patterns"]
    summ = json.loads((rd / "analysis" / "summary.json").read_text())
    sub = pd.read_csv(rd / "subgroup_recall.csv")
    lat = pd.read_csv(rd / "latency.csv")
    m = lm["methods"]
    sev = sub[sub.dimension == "severity"].pivot_table(
        index="group", columns="method", values="recall"
    )
    h = summ["headline"]
    c = prof["counts"]

    app_url = cfg["app_url"]
    app_link = (
        f'<a class="btn" href="{esc(app_url)}">Open the interactive app</a>'
        if app_url and app_url != "APP_URL"
        else '<a class="btn" href="#app">Run the interactive app</a>'
    )
    a_ex = (REPO / "examples" / "pattern_a" / "example_1_hospital_ADT_A04.hl7").read_text()
    a_ex = "\n".join(ln for ln in a_ex.splitlines() if not ln.startswith("#"))
    a_uuid = next(ln for ln in a_ex.splitlines() if ln.startswith("PV1")).split("|")[50]
    a_ex = esc(a_ex).replace("^^^EMSUUID^VN", "<mark>^^^EMSUUID^VN</mark>")
    c_ex = json.loads(
        (REPO / "examples" / "pattern_c" / "example_1_transaction_bundle.json").read_text()
    )
    enc = c_ex["entry"][0]["resource"]
    c_snip = esc(
        json.dumps({"resourceType": "Encounter", "identifier": enc["identifier"]}, indent=2)
    )
    c_snip = c_snip.replace(esc(EMS_UUID_SYSTEM), f"<mark>{esc(EMS_UUID_SYSTEM)}</mark>")

    body = f"""
<section class="hero" style="margin-top:8px">
  <h1>One identifier, carried from the ambulance to the emergency department.</h1>
  <p class="lede">Injury data for motor-vehicle crashes and falls are split between EMS patient care reports
  and hospital ED records. This lab simulates how the <strong>non-identifying UUID</strong> that an ePCR already
  assigns to every report could travel into the ED record — and what exact, immediate linkage enables compared
  with probabilistic matching on names and birth dates.</p>
  <div class="cta"><a class="btn primary" href="#results">See the results</a>{app_link}
  <a class="btn" href="{esc(cfg["repo_url"])}">View source</a></div>
  <div class="kpis">
    <div class="kpi"><div class="v">{c["injury_events"]:,}</div><div class="l">synthetic injury events</div></div>
    <div class="kpi"><div class="v">{c["ems_records"]:,}</div><div class="l">EMS ePCR records</div></div>
    <div class="kpi"><div class="v">{c["ed_encounters"]:,}</div><div class="l">ED encounters</div></div>
    <div class="kpi"><div class="v">{c["true_links"]:,}</div><div class="l">true EMS→ED links</div></div>
  </div>
</section>

<section>
  <h2>The problem and the idea</h2>
  <div class="grid">
    <div class="card"><h3>Siloed data</h3><p>EMS knows the mechanism, scene, vitals, field-triage criteria and
    alcohol/drug indicators. The ED knows diagnoses and outcomes. Neither alone answers “what happened to the
    patients EMS triaged as high-risk?”</p></div>
    <div class="card"><h3>Probabilistic matching</h3><p>Today the two are often joined after the fact by matching
    names, birth dates and times — which degrades exactly where data quality is worst: unidentified trauma
    patients, aliases, name variants, and some demographic groups.</p></div>
    <div class="card"><h3>Carry one identifier</h3><p>NEMSIS v3.5 already requires a UUID on every
    <code>PatientCareReport</code>. If integration carries it into the ED encounter, the join is exact and
    available at the encounter — with no names exchanged for linkage.</p></div>
  </div>
</section>

<section id="patterns">
  <h2>Three integration patterns</h2>
  <p>Each pattern was simulated with configurable failure rates. Example messages and bundles are in
  <a href="examples/index.html">examples</a>.</p>
  <div class="diagram">{patterns_svg()}</div>
  <div class="grid" style="margin-top:16px">
    <div class="card"><h3>A · Point-to-point HL7 v2</h3><p>ePCR → hospital <code>ADT^A05</code>; the UUID lands in
    <code>PV1-50</code> (Alternate Visit ID) under assigning authority <code>EMSUUID</code>.</p>
    <p>Simulated carry rate: <strong>{plog["A"]["observed_carry_rate"]:.1%}</strong></p></div>
    <div class="card"><h3>B · HIE intermediary</h3><p>EMS and ED <code>ADT^A04</code> → HIE matcher → UUID written
    back with <code>ADT^A08</code>. Timing windows and matching cause misses.</p>
    <p>Simulated carry rate: <strong>{plog["B"]["observed_carry_rate"]:.1%}</strong></p></div>
    <div class="card"><h3>C · FHIR R4 API</h3><p>Integration service PUTs the ED <code>Encounter</code> with an
    additional <code>identifier</code> in its own system URI; bundles validated with fhir.resources.</p>
    <p>Simulated carry rate: <strong>{plog["C"]["observed_carry_rate"]:.1%}</strong></p></div>
  </div>
  <h3>Where the UUID lives — Pattern A (hospital ADT^A04)</h3>
  <pre>{a_ex}</pre>
  <p>Field breakdown: <code>PV1-19</code> = hospital visit number · <code>PV1-50</code> =
  <code>{esc(a_uuid)}</code> (component 4 = assigning authority <code>EMSUUID</code>, component 5 = type <code>VN</code>).</p>
  <h3>Where the UUID lives — Pattern C (FHIR Encounter.identifier)</h3>
  <pre>{c_snip}</pre>
</section>

<section id="results">
  <h2>Headline linkage results</h2>
  <p>Evaluated against {lm["n_true_links"]:,} true EMS→ED transport links (Splink threshold
  {lm["match_threshold"]}). False-match rate = share of declared links that are wrong.</p>
  {results_table(m)}
  <div class="grid" style="margin-top:16px">
    <div class="card"><h3>Exact, but only if it arrives</h3><p>UUID joins never produce false matches here
    (precision 1.000); their recall equals the share of encounters the integration actually delivered.</p></div>
    <div class="card"><h3>Probabilistic misses the sickest</h3><p>Splink recall for <strong>critical</strong> injuries:
    <strong>{sev.loc["critical", "splink_time"]:.1%}</strong> vs <strong>{sev.loc["critical", "det_C"]:.1%}</strong>
    with the Pattern C UUID — trauma aliases and “unknown” patients have nothing to match on.</p></div>
    <div class="card"><h3>Better together</h3><p>UUID first, Splink for the rest:
    recall <strong>{m["hybrid_C"]["recall"]:.1%}</strong>, precision <strong>{m["hybrid_C"]["precision"]:.1%}</strong>.</p></div>
  </div>
  {fig_html(charts.scoreboard(m), "fig-scoreboard")}
  {fig_html(charts.subgroup_dots(sub, "severity"), "fig-severity")}
  {fig_html(charts.subgroup_dots(sub, "race_eth"), "fig-race")}
  <p class="note">How estimates move with the linkage method (demonstration): among EMS patients with
  high-risk field-triage criteria, the share admitted, transferred or died is
  <strong>{h["truth"]["high_risk_triage_admit_transfer_or_died"]:.1%}</strong> with ground-truth links,
  <strong>{h["det_C"]["high_risk_triage_admit_transfer_or_died"]:.1%}</strong> with UUID links and
  <strong>{h["splink_time"]["high_risk_triage_admit_transfer_or_died"]:.1%}</strong> with Splink links —
  because the records probabilistic matching drops are not missing at random.</p>
  {fig_html(charts.latency(lat), "fig-latency")}
  <p>Latency is a <strong>labelled assumption</strong> (deterministic links at the encounter; probabilistic
  linkage as an annual batch {cfg.get("_prob_lag", 18)} months after the data year closes), configurable in
  <code>config/default.yaml</code>.</p>
</section>

<section id="app">
  <h2>Explore it</h2>
  <div class="grid">
    <div class="card"><h3>Interactive app</h3><p>Pattern explorer, linkage scoreboard, bias tab and
    “what linkage enables” — runs offline from committed files.</p>
    <p>{('<a href="' + esc(app_url) + '">Open the hosted app</a>') if app_url != "APP_URL" else "Hosted app: <code>APP_URL</code> (placeholder)."}</p>
    <pre>pip install -r requirements.txt
make app</pre></div>
    <div class="card"><h3>Reproduce everything</h3><p>Fixed seed, sorted exports — the same commands produce the
    same files.</p><pre>make data simulate link analyze
make test
make site</pre></div>
    <div class="card"><h3>Documentation</h3><p>Reusable templates for implementers.</p>
    <ul>{"".join(f'<li><a href="docs/{k}.html">{esc(v)}</a></li>' for k, v in DOCS)}</ul></div>
  </div>
</section>
"""
    head = '<script src="assets/plotly.min.js"></script>'
    (out / "index.html").write_text(
        page(
            cfg["site_title"],
            body,
            "",
            cfg,
            "Simulating EMS-to-ED record linkage with a shared UUID on synthetic data.",
            head,
        ),
        encoding="utf-8",
    )


def build_docs(cfg: dict, out: Path) -> None:
    d = out / "docs"
    d.mkdir(parents=True, exist_ok=True)
    items = []
    for key, title in DOCS:
        src = REPO / "docs" / f"{key}.md"
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8")
        body = f'<article class="doc">{render_markdown(text, cfg)}</article>'
        head = MERMAID_HEAD if "```mermaid" in text else ""
        (d / f"{key}.html").write_text(
            page(f"{title} — {cfg['site_title']}", body, "../", cfg, title, head), encoding="utf-8"
        )
        items.append(f'<li><a href="{key}.html">{esc(title)}</a></li>')
    body = f'<article class="doc"><h1>Documentation</h1><p>{esc(DISCLAIMER)}</p><ul>{"".join(items)}</ul></article>'
    (d / "index.html").write_text(
        page(f"Docs — {cfg['site_title']}", body, "../", cfg, "Documentation"), encoding="utf-8"
    )


def build_examples(cfg: dict, out: Path) -> None:
    dst = out / "examples"
    shutil.copytree(REPO / "examples", dst, dirs_exist_ok=True)
    secs = []
    names = {
        "pattern_a": "Pattern A — point-to-point HL7 v2",
        "pattern_b": "Pattern B — HIE intermediary",
        "pattern_c": "Pattern C — FHIR R4 API",
    }
    for key, title in names.items():
        files = sorted((REPO / "examples" / key).glob("*"))
        lis = "".join(f'<li><a href="{key}/{f.name}">{esc(f.name)}</a></li>' for f in files)
        first = files[0].read_text(encoding="utf-8") if files else ""
        secs.append(f"<h2>{esc(title)}</h2><ul class='files'>{lis}</ul><pre>{esc(first)}</pre>")
    body = (
        f'<article class="doc"><h1>Example messages and bundles</h1><p>{esc(DISCLAIMER)} '
        "HL7 v2 files show one segment per line (carriage-return separated on the wire). "
        "FHIR files are R4 JSON validated with fhir.resources.</p>" + "".join(secs) + "</article>"
    )
    (dst / "index.html").write_text(
        page(f"Examples — {cfg['site_title']}", body, "../", cfg, "Examples"), encoding="utf-8"
    )


def build(out: Path) -> Path:
    cfg = yaml.safe_load((SRC / "site.yaml").read_text())
    dcfg = yaml.safe_load((REPO / "config" / "default.yaml").read_text())
    cfg["_prob_lag"] = dcfg["latency_assumptions"]["probabilistic_months_after_year_end"]
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    for f in ("style.css", "site.js"):
        shutil.copy(SRC / "assets" / f, out / "assets" / f)
    (out / "assets" / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
    shutil.copytree(REPO / "results", out / "results")
    build_index(cfg, out)
    build_docs(cfg, out)
    build_examples(cfg, out)
    (out / ".nojekyll").write_text("")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO / "_site"))
    args = ap.parse_args(argv)
    out = build(Path(args.out))
    print(f"[site] built {out}")


if __name__ == "__main__":
    main()

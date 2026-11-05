"""EMS–ED Linkage Lab — Streamlit explorer.

Runs fully offline from committed files (results/ and examples/). No data are generated or
downloaded at runtime.   Run:  make app   (or: streamlit run app/streamlit_app.py)

Synthetic data — for demonstration only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from common import AFFILIATION, DISCLAIMER, EMS_UUID_SYSTEM, charts  # noqa: E402

RESULTS, EXAMPLES = REPO / "results", REPO / "examples"

st.set_page_config(page_title="EMS–ED Linkage Lab", page_icon="🚑", layout="wide")


@st.cache_data
def load_json(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


@st.cache_data
def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RESULTS / name)


def plot(fig):
    st.plotly_chart(fig, width="stretch", theme=None)


# ----------------------------------------------------------------------------- chrome
st.warning(f"**{DISCLAIMER}** No real patients, agencies or hospitals are represented.", icon="⚠️")
with st.sidebar:
    st.markdown("### EMS–ED Linkage Lab")
    st.caption(DISCLAIMER)
    st.info(AFFILIATION)
    st.markdown(
        "**Idea:** the ePCR already assigns each patient care report a UUID (NEMSIS v3.5 "
        "`PatientCareReport/@UUID`). If that one non-identifying identifier travels into the ED "
        "record, EMS and ED data can be joined exactly, at the encounter."
    )
    st.markdown("**Author:** Sai Kurmana, MPH, MS, CPHIMS")
    st.markdown(
        "[Docs](https://github.com/saikurmana/ems-ed-linkage-lab/tree/main/docs) · "
        "[Standards references](https://github.com/saikurmana/ems-ed-linkage-lab/blob/main/docs/standards_references.md)"
    )

st.title("EMS–ED Linkage Lab")
st.caption(
    "Deterministic UUID linkage vs probabilistic matching for motor-vehicle-crash and fall "
    "injuries — on synthetic data."
)

profile = load_json("data_profile.json")
c = profile["counts"]
cols = st.columns(5)
for col, (label, key) in zip(
    cols,
    [
        ("Injury events", "injury_events"),
        ("EMS records", "ems_records"),
        ("ED encounters", "ed_encounters"),
        ("True EMS→ED links", "true_links"),
        ("ED visits without EMS", "ed_without_ems"),
    ],
    strict=True,
):
    col.metric(label, f"{c[key]:,}")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Pattern explorer", "Linkage scoreboard", "Bias", "What linkage enables"]
)

# ----------------------------------------------------------------------------- tab 1
PATTERN_INFO = {
    "A — Point-to-point HL7 v2": {
        "dir": "pattern_a",
        "key": "A",
        "where": "ED record **PV1-50 (Alternate Visit ID)**, CX with assigning authority `EMSUUID` "
        "and identifier type `VN` — a documented local convention.",
        "flow": [
            "ePCR system → hospital interface engine: **ADT^A05** (pre-admit) with the UUID in PV1-50",
            "Interface engine parses and holds the pre-admit",
            "ED registration merges the pre-admit into the ED encounter → UUID kept in PV1-50",
            "Hospital ADT^A04 feed now carries the UUID downstream",
        ],
        "needle": "^^^EMSUUID^VN",
    },
    "B — HIE intermediary": {
        "dir": "pattern_b",
        "key": "B",
        "where": "HIE writes the UUID back into the ED record's **PV1-50** via **ADT^A08** after matching "
        "the EMS and ED ADT messages on demographics + time.",
        "flow": [
            "ePCR → HIE: **ADT^A04** (UUID = EMS visit number, PV1-19; destination PV1-37)",
            "ED → HIE: **ADT^A04** at registration",
            "HIE matcher: same destination, handoff within tolerance, inside match window, demographic score",
            "HIE → hospital: **ADT^A08** update with the UUID in PV1-50",
        ],
        "needle": "EMSUUID",
    },
    "C — FHIR API (integration service)": {
        "dir": "pattern_c",
        "key": "C",
        "where": f"An additional **Encounter.identifier** with `system = {EMS_UUID_SYSTEM}` and "
        "`use = secondary`, next to the hospital's own visit-number identifier.",
        "flow": [
            "At transfer of care the vendor integration service finds the ED Encounter",
            "Sends a FHIR R4 **transaction Bundle**: PUT Encounter with the extra identifier",
            "Hospital keeps the identifier on the Encounter (validated with fhir.resources)",
            "Downstream exports (collection Bundle) carry the UUID",
        ],
        "needle": EMS_UUID_SYSTEM,
    },
}
with tab1:
    choice = st.radio("Integration pattern", list(PATTERN_INFO), horizontal=True)
    info = PATTERN_INFO[choice]
    left, right = st.columns([1, 2])
    with left:
        st.markdown("#### Data flow")
        for i, step in enumerate(info["flow"], 1):
            st.markdown(f"{i}. {step}")
        st.markdown("#### Where the UUID lives")
        st.success(info["where"])
        log = load_json("pattern_logs.json")["patterns"][info["key"]]
        st.markdown("#### Simulated outcome")
        st.json({k: v for k, v in log.items() if not k.startswith("n_")}, expanded=False)
    with right:
        files = sorted((EXAMPLES / info["dir"]).glob("*"))
        names = [f.name for f in files]
        fname = st.selectbox("Example message / bundle", names)
        text = (EXAMPLES / info["dir"] / fname).read_text(encoding="utf-8")
        if fname.endswith(".json"):
            st.code(text, language="json")
            bundle = json.loads(text)
            for e in bundle["entry"]:
                if e["resource"]["resourceType"] == "Encounter":
                    st.markdown("**UUID-bearing identifier:**")
                    st.json(
                        [
                            i
                            for i in e["resource"]["identifier"]
                            if i.get("system") == EMS_UUID_SYSTEM
                        ]
                    )
        else:
            st.code(text, language="text")
            hits = [ln for ln in text.splitlines() if info["needle"] in ln]
            for ln in hits:
                fields = ln.split("|")
                seg = fields[0]
                rows = [
                    {"field": f"{seg}-{i}", "value": v} for i, v in enumerate(fields) if i and v
                ]
                if seg == "MSH":  # MSH-1 is the field separator itself, so indices shift by one
                    rows = [
                        {"field": f"MSH-{i + 1}", "value": v}
                        for i, v in enumerate(fields)
                        if i and v
                    ]
                st.markdown(
                    f"**{seg} segment — populated fields** (UUID highlighted by `EMSUUID`):"
                )
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    plot(charts.funnel(load_json("pattern_logs.json")["patterns"]))

# ----------------------------------------------------------------------------- tab 2
with tab2:
    lm = load_json("linkage_metrics.json")
    m = lm["methods"]
    st.markdown(
        f"Evaluated against **{lm['n_true_links']:,}** true EMS→ED transport links. "
        f"Splink threshold = {lm['match_threshold']}."
    )
    tbl = pd.DataFrame(
        [
            {
                "Method": v["label"],
                "Precision": v["precision"],
                "Recall": v["recall"],
                "F1": v["f1"],
                "False-match rate": v["false_match_rate"],
                "Declared links": v["n_declared_links"],
            }
            for v in m.values()
        ]
    )
    st.dataframe(
        tbl.style.format({c: "{:.3f}" for c in ["Precision", "Recall", "F1", "False-match rate"]}),
        hide_index=True,
        width="stretch",
    )
    plot(charts.scoreboard(m))
    a, b = st.columns(2)
    with a:
        plot(charts.threshold_sweep(load_csv("threshold_sweep.csv")))
    with b:
        rt = load_json("runtime.json")
        st.markdown("#### Runtime (seconds)")
        st.caption(rt["note"])
        st.dataframe(
            pd.DataFrame({"method": list(rt["seconds"]), "seconds": list(rt["seconds"].values())}),
            hide_index=True,
            width="stretch",
        )
        st.markdown("#### Why Splink (time) missed links")
        mr = lm["splink_time_recall_by_data_quality_issue"]
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "issue": k,
                        "true links with issue": v["n_true_links_with_issue"],
                        "Splink recall": v["splink_time_recall_when_present"],
                    }
                    for k, v in mr.items()
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    with st.expander("Definitions"):
        st.json(lm["definitions"])

# ----------------------------------------------------------------------------- tab 3
with tab3:
    st.markdown(
        "Data-quality problems were injected at **higher rates for some subgroups** (see "
        "`config/default.yaml → data_quality.multipliers`). Deterministic UUID carry fails at random "
        "(by design here), so its recall is flat across groups; probabilistic recall inherits the "
        "unequal data quality. Groups use the **true** (latent) attributes from the ground truth."
    )
    sub = load_csv("subgroup_recall.csv")
    dim = st.selectbox(
        "Subgroup dimension", list(charts.GROUP_LABEL), format_func=charts.GROUP_LABEL.get
    )
    plot(charts.subgroup_dots(sub, dim))
    piv = sub[sub.dimension == dim].pivot_table(index="group", columns="method", values="recall")
    gap = (piv.max() - piv.min()).rename("max − min recall gap").to_frame().T
    st.markdown("**Recall gap across groups (percentage points × 100)**")
    st.dataframe(gap.style.format("{:.3f}"), width="stretch")
    st.dataframe(piv.style.format("{:.3f}"), width="stretch")

# ----------------------------------------------------------------------------- tab 4
with tab4:
    summ = json.loads((RESULTS / "analysis" / "summary.json").read_text(encoding="utf-8"))
    st.info(
        "These are **demonstrations of what linkage makes possible, not findings.** Each "
        "question is answered under ground-truth, UUID and Splink linkage so you can see how the "
        "linkage method moves the answer."
    )
    for qid, q in summ["questions"].items():
        st.markdown(f"#### {q}")
        df = pd.read_csv(RESULTS / "analysis" / f"{qid}.csv")
        st.dataframe(df, hide_index=True, width="stretch")
        if qid == "q2_outcomes_by_arrival":
            st.caption("⚠️ " + summ["confounding_note"])
    st.markdown("#### Data latency (assumption)")
    st.caption(
        "Deterministic links exist at the encounter; probabilistic linkage is modelled as an annual "
        "batch run some months after the data year closes. Configurable in "
        "`config/default.yaml → latency_assumptions`. This is an ASSUMPTION, not a measurement."
    )
    plot(charts.latency(load_csv("latency.csv")))

st.divider()
st.caption(f"{DISCLAIMER} {AFFILIATION}")

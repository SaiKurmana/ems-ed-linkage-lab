"""Plotly figures shared by the Streamlit app and the static site.

Colors follow a validated categorical palette with a FIXED method -> slot mapping (color
follows the entity, never its rank). Dark-mode steps are swapped in by the site's JS.
Every figure carries the synthetic-data label in its title.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from common import DISCLAIMER

LIGHT = {
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
    "magenta": "#e87ba4",
    "green": "#008300",
}
DARK = {
    "#2a78d6": "#3987e5",
    "#eb6834": "#d95926",
    "#1baf7a": "#199e70",
    "#eda100": "#c98500",
    "#e87ba4": "#d55181",
    "#008300": "#008300",
}
TEXT, TEXT_2, GRID = "#0b0b0b", "#52514e", "rgba(82,81,78,0.18)"

METHOD_COLOR = {
    "det_A": LIGHT["blue"],
    "det_B": LIGHT["orange"],
    "det_C": LIGHT["aqua"],
    "splink_time": LIGHT["yellow"],
    "splink_date": LIGHT["magenta"],
    "hybrid_C": LIGHT["green"],
}
METHOD_SHORT = {
    "det_A": "UUID · A (HL7 v2)",
    "det_B": "UUID · B (HIE)",
    "det_C": "UUID · C (FHIR)",
    "splink_time": "Splink (time)",
    "splink_date": "Splink (date only)",
    "hybrid_C": "Hybrid (C + Splink)",
}
GROUP_LABEL = {
    "race_eth": "Race / ethnicity (true)",
    "age_group": "Age group",
    "urbanicity": "Urbanicity",
    "severity": "Injury severity (latent)",
}
GROUP_ORDER = {
    "age_group": ["0-17", "18-44", "45-64", "65+"],
    "severity": ["minor", "moderate", "severe", "critical"],
    "urbanicity": ["urban", "rural"],
    "race_eth": ["White", "Black", "Hispanic", "Asian", "AIAN", "NHPI"],
}


def _layout(fig: go.Figure, title: str, height: int = 380, **kw) -> go.Figure:
    fig.update_layout(
        title={
            "text": f"{title}<br><sup>{DISCLAIMER}</sup>",
            "x": 0,
            "xanchor": "left",
            "font": {"size": 15, "color": TEXT},
        },
        font={
            "family": "Inter, system-ui, -apple-system, Segoe UI, sans-serif",
            "size": 12,
            "color": TEXT_2,
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 10, "r": 10, "t": 70, "b": 10},
        height=height,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": -0.28,
            "x": 0,
            "font": {"color": TEXT_2},
        },
        hoverlabel={"font": {"family": "Inter, system-ui, sans-serif"}},
        bargap=0.25,
        bargroupgap=0.08,
        **kw,
    )
    axis = {
        "gridcolor": GRID,
        "zeroline": False,
        "linecolor": GRID,
        "automargin": True,
        "tickfont": {"color": TEXT_2},
        "title": {"font": {"color": TEXT_2}},
    }
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def scoreboard(metrics: dict) -> go.Figure:
    order = [m for m in METHOD_SHORT if m in metrics]
    fig = go.Figure()
    for metric, color in (("precision", LIGHT["blue"]), ("recall", LIGHT["orange"])):
        vals = [metrics[m][metric] for m in order]
        fig.add_bar(
            y=[METHOD_SHORT[m] for m in order],
            x=vals,
            name=metric.capitalize(),
            orientation="h",
            marker={"color": color, "line": {"width": 0}, "cornerradius": 4},
            text=[f"{v:.3f}" for v in vals],
            textposition="outside",
            textfont={"color": TEXT_2},
            hovertemplate="%{y}<br>" + metric + ": %{x:.3f}<extra></extra>",
        )
    fig.update_xaxes(range=[0, 1.12], tickformat=".0%")
    fig.update_yaxes(autorange="reversed")
    return _layout(fig, "Precision and recall by linkage method", height=430, barmode="group")


def subgroup_dots(
    sub: pd.DataFrame, dimension: str, methods=("det_C", "splink_time", "splink_date")
) -> go.Figure:
    d = sub[(sub.dimension == dimension) & (sub.method.isin(methods))]
    groups = [g for g in GROUP_ORDER.get(dimension, sorted(d.group.unique())) if g in set(d.group)]
    fig = go.Figure()
    for m in methods:
        dm = d[d.method == m].set_index("group").reindex(groups)
        fig.add_scatter(
            x=dm.recall,
            y=groups,
            mode="markers",
            name=METHOD_SHORT[m],
            marker={"size": 11, "color": METHOD_COLOR[m], "line": {"width": 2, "color": "#fcfcfb"}},
            customdata=dm.n_true_links,
            hovertemplate="%{y} · "
            + METHOD_SHORT[m]
            + "<br>recall %{x:.3f} (n=%{customdata})<extra></extra>",
        )
    fig.update_xaxes(tickformat=".0%", range=[max(0, float(d.recall.min()) - 0.05), 1.02])
    fig.update_yaxes(autorange="reversed")
    return _layout(
        fig,
        f"Recall by {GROUP_LABEL.get(dimension, dimension).lower()}",
        height=150 + 42 * len(groups),
    )


def latency(lat: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for m in [x for x in METHOD_SHORT if x in set(lat.method)]:
        d = lat[lat.method == m]
        fig.add_scatter(
            x=d.months_since_encounter,
            y=d.share_of_true_links_available,
            mode="lines",
            name=METHOD_SHORT[m],
            line={"width": 2, "color": METHOD_COLOR[m], "shape": "hv"},
            hovertemplate=METHOD_SHORT[m] + "<br>month %{x}: %{y:.1%}<extra></extra>",
        )
    fig.update_xaxes(title="Months since the encounter", dtick=6)
    fig.update_yaxes(title="Share of true links available", tickformat=".0%", range=[0, 1.02])
    return _layout(
        fig,
        "When can a linked record be analysed? (latency ASSUMPTIONS)",
        height=400,
        hovermode="x unified",
    )


def funnel(pattern_logs: dict) -> go.Figure:
    stages = {
        "A": [
            ("Transported", "n_transported"),
            ("Interface live", "interface_live"),
            ("Message delivered", "message_delivered"),
            ("Registration merge kept UUID", "registration_merge"),
        ],
        "C": [
            ("Transported", "n_transported"),
            ("API enabled", "api_enabled"),
            ("API call succeeded", "api_call_success"),
            ("Identifier retained", "identifier_retained"),
        ],
    }
    fig = go.Figure()
    for k, color in (("A", METHOD_COLOR["det_A"]), ("C", METHOD_COLOR["det_C"])):
        log = pattern_logs[k]
        fig.add_bar(
            x=[s[0] for s in stages[k]],
            y=[log[s[1]] for s in stages[k]],
            name=f"Pattern {k}",
            marker={"color": color, "cornerradius": 4},
            hovertemplate=f"Pattern {k}<br>" + "%{x}: %{y:,}<extra></extra>",
        )
    return _layout(
        fig, "Where the UUID is lost: failure stages (Patterns A and C)", barmode="group"
    )


def threshold_sweep(sweep: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for m in ("splink_time", "splink_date"):
        d = sweep[sweep.method == m]
        fig.add_scatter(
            x=d.recall,
            y=d.precision,
            mode="lines+markers",
            name=METHOD_SHORT[m],
            line={"width": 2, "color": METHOD_COLOR[m]},
            marker={"size": 8},
            customdata=d.threshold,
            hovertemplate="threshold %{customdata}<br>recall %{x:.3f}<br>precision %{y:.3f}<extra></extra>",
        )
    fig.update_xaxes(title="Recall", tickformat=".0%")
    fig.update_yaxes(title="Precision", tickformat=".1%")
    return _layout(fig, "Splink precision–recall across match-probability thresholds")

"""Interactive, self-contained HTML dashboard (Plotly) for the F1 OPEX pipeline.

A pure presentation layer over the analysis outputs: a branded Red Bull "cockpit" with
animated KPI tiles, a budget-utilisation gauge, four interactive charts, a live department
filter, per-chart view tabs, and click-to-expand savings drill-downs — emitted as a single
offline-capable ``.html`` file (plotly.js inlined once). Mirrors the Excel reporter's
split — analysis *computes*, this module *renders* — and reuses the brand palette from
``constants.py``.

Interactivity is driven by a small vanilla-JS controller (no external libraries): the
analysis outputs are embedded once as a JSON ``<script>`` payload, and the controller
rebuilds figures with ``Plotly.react`` and recomputes the affected KPIs entirely
client-side. The four charts are also rendered server-side so the page is meaningful with
JavaScript disabled.
"""

from __future__ import annotations

import json
from datetime import datetime
from string import Template
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from analysis import KpiSummary, Opportunity
from constants import (
    COLOR_DASH_BG,
    COLOR_DASH_CHARCOAL,
    COLOR_DASH_CRIMSON,
    COLOR_DASH_FG,
    COLOR_DASH_GLOW,
    COLOR_DASH_GRID,
    COLOR_DASH_MUTED,
    COLOR_DASH_NEON,
    COLOR_DASH_SCAN,
    COLOR_DASH_SURFACE,
    COLOR_DASH_TAN,
    COLOR_DASH_TITANIUM,
    COLOR_NEGATIVE,
    COLOR_POSITIVE,
    DASH_FONT,
)
from exceptions import DashboardError
from formatting import compact_money

# Spend-mix donut ramp — crimson largest slice through tan/grey to bone; also colours the
# department filter-chip dots and the client-side donut.
_DEPT_PALETTE: tuple[str, ...] = (
    "#B3122B",
    "#C7A06A",
    "#9DA3A8",
    "#D2696E",
    "#C9B9A6",
    "#6E7378",
    "#8E0E22",
    "#ECE5D5",
)

_PLOTLY_CONFIG: dict[str, Any] = {"displayModeBar": False, "responsive": True}


def _dept_color_map(dept_summary: pd.DataFrame) -> dict[str, str]:
    """Stable department→colour assignment, ranked by actual spend.

    One shared mapping keeps the donut ramp (crimson largest → bone smallest), makes each
    filter chip's dot match its donut slice, and pins a department to one colour no matter
    how the client-side filter re-sorts the chart.
    """
    ranked = dept_summary.sort_values("Actual Amount", ascending=False)["Department"]
    return {str(d): _DEPT_PALETTE[i % len(_DEPT_PALETTE)] for i, d in enumerate(ranked)}


# Stable div ids so the JS controller can target each figure with Plotly.react.
_DIV_BUDGET = "fig-budget"
_DIV_MIX = "fig-mix"
_DIV_MONTHLY = "fig-monthly"
_DIV_VARIANCE = "fig-variance"
_DIV_GAUGE = "fig-gauge"


def _style(fig: go.Figure, height: int) -> go.Figure:
    """Apply the shared dark-cockpit look to a figure — the HTML analogue of _style_chart."""
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=18, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLOR_DASH_FG, family=DASH_FONT, size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(
            bgcolor=COLOR_DASH_SURFACE,
            bordercolor="rgba(236,229,213,0.18)",
            font=dict(size=12, family=DASH_FONT, color=COLOR_DASH_FG),
        ),
    )
    # Bone-tinted dotted hairlines instead of solid crimson — the grid recedes so the
    # data carries the colour.
    axis = dict(
        gridcolor="rgba(236,229,213,0.07)",
        griddash="dot",
        gridwidth=1,
        zerolinecolor="rgba(236,229,213,0.18)",
        linecolor=COLOR_DASH_GRID,
        color=COLOR_DASH_MUTED,
        ticklabelstandoff=6,
    )
    fig.update_xaxes(**axis)
    fig.update_yaxes(**axis)
    return fig


def _budget_actual_fig(dept_summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        name="Budget",
        x=dept_summary["Department"],
        y=dept_summary["Budgeted Amount"],
        marker=dict(color=COLOR_DASH_TITANIUM, opacity=0.92, line=dict(width=0)),
        hovertemplate="Budget  $%{y:,.0f}<extra></extra>",
    )
    fig.add_bar(
        name="Actual",
        x=dept_summary["Department"],
        y=dept_summary["Actual Amount"],
        marker=dict(color=COLOR_DASH_CRIMSON, line=dict(width=0)),
        hovertemplate="Actual  $%{y:,.0f}<extra></extra>",
    )
    fig.update_layout(
        barmode="group",
        bargap=0.34,
        bargroupgap=0.08,
        barcornerradius=4,
        hovermode="x unified",
    )
    fig.update_xaxes(tickangle=-30)
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return _style(fig, 360)


def _spend_mix_fig(dept_summary: pd.DataFrame) -> go.Figure:
    # Pre-sorted descending (instead of Plotly's sort) so the palette stays aligned
    # to slice order. Slices rest flush — the JS controller animates a hover pull
    # and an entrance sweep, so no slice looks pre-selected.
    ranked = dept_summary.sort_values("Actual Amount", ascending=False)
    fig = go.Figure(
        go.Pie(
            labels=ranked["Department"],
            values=ranked["Actual Amount"],
            hole=0.62,
            sort=False,
            direction="clockwise",
        )
    )
    color_map = _dept_color_map(dept_summary)
    fig.update_traces(
        marker=dict(
            colors=[color_map[str(d)] for d in ranked["Department"]],
            line=dict(color=COLOR_DASH_BG, width=3),
        ),
        textinfo="percent",
        textfont=dict(size=11, family=DASH_FONT),
        insidetextorientation="horizontal",
        domain=dict(x=[0.0, 0.66]),
        hovertemplate="%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>",
    )
    total = float(dept_summary["Actual Amount"].sum())
    fig = _style(fig, 360)
    fig.update_layout(
        legend=dict(orientation="v", x=0.72, y=0.5, font=dict(size=11)),
        annotations=[
            dict(
                text=f"<b>{compact_money(total)}</b><br>"
                f"<span style='font-size:11px;color:{COLOR_DASH_MUTED}'>Actual spend</span>",
                x=0.33,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=19, color=COLOR_DASH_FG),
            )
        ],
    )
    return fig


def _monthly_trend_fig(monthly_trend: pd.DataFrame) -> go.Figure:
    months = monthly_trend["Month Name"]
    fig = go.Figure()
    fig.add_scatter(
        name="Budget",
        x=months,
        y=monthly_trend["Budgeted Amount"],
        mode="lines+markers",
        line=dict(color=COLOR_DASH_TITANIUM, width=2.5, shape="spline", smoothing=0.75),
        marker=dict(size=6, line=dict(color=COLOR_DASH_BG, width=1.5)),
        hovertemplate="Budget  $%{y:,.0f}<extra></extra>",
    )
    fig.add_scatter(
        name="Actual",
        x=months,
        y=monthly_trend["Actual Amount"],
        mode="lines+markers",
        # Same colour as the "Actual" bar series — one colour per series across charts.
        line=dict(color=COLOR_DASH_CRIMSON, width=3, shape="spline", smoothing=0.75),
        marker=dict(size=7, line=dict(color=COLOR_DASH_BG, width=1.5)),
        fill="tozeroy",
        fillcolor="rgba(179,18,43,0.10)",
        hovertemplate="Actual  $%{y:,.0f}<extra></extra>",
    )
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return _style(fig, 340)


def _grade_alpha(value: float, max_abs: float) -> float:
    """Map |value| to a fill opacity so bar colour intensity tracks magnitude."""
    if max_abs <= 0:
        return 1.0
    return 0.45 + 0.55 * (abs(value) / max_abs)


def _variance_ranking_fig(dept_summary: pd.DataFrame) -> go.Figure:
    # Ascending → most negative at the bottom, biggest overspend at the top.
    ranked = dept_summary.sort_values("Variance")
    max_abs = float(ranked["Variance"].abs().max())
    colors = [
        (
            f"rgba(214,32,63,{_grade_alpha(v, max_abs):.2f})"
            if v > 0
            else f"rgba(157,163,168,{_grade_alpha(v, max_abs):.2f})"
        )
        for v in ranked["Variance"]
    ]
    fig = go.Figure()
    fig.add_bar(
        orientation="h",
        y=ranked["Department"],
        x=ranked["Variance"],
        marker=dict(color=colors, line=dict(width=0)),
        text=[compact_money(v) for v in ranked["Variance"]],
        textposition="outside",
        textfont=dict(size=11, family=DASH_FONT),
        cliponaxis=False,
        hovertemplate="%{y}<br>Variance $%{x:,.0f}<extra></extra>",
    )
    fig.update_layout(showlegend=False, bargap=0.32, barcornerradius=3)
    fig.update_xaxes(
        tickprefix="$",
        tickformat="~s",
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor=COLOR_DASH_MUTED,
    )
    fig = _style(fig, 420)
    # Pad the x-range and right margin so the outside $-labels never clip the card edge.
    vmax = float(max(ranked["Variance"].max(), 0.0))
    vmin = float(min(ranked["Variance"].min(), 0.0))
    pad = (vmax - vmin) * 0.18 or 1.0
    fig.update_layout(margin=dict(l=12, r=64, t=8, b=8))
    fig.update_xaxes(range=[vmin - pad, vmax + pad])
    return fig


def _utilization_gauge_fig(kpis: KpiSummary) -> go.Figure:
    """Radial gauge of actual ÷ budget (%), with a threshold zone at 100%."""
    budget = kpis["total_budget"]
    pct = (kpis["total_actual"] / budget * 100.0) if budget else 0.0
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=pct,
            number=dict(suffix="%", font=dict(size=34, color=COLOR_DASH_FG, family=DASH_FONT)),
            delta=dict(
                reference=100,
                suffix="%",
                font=dict(size=13),
                increasing=dict(color=COLOR_NEGATIVE),  # above budget is bad
                decreasing=dict(color=COLOR_POSITIVE),
            ),
            gauge=dict(
                axis=dict(
                    range=[0, 150],
                    tickcolor="rgba(236,229,213,0.25)",
                    ticksuffix="%",
                    tickfont=dict(color=COLOR_DASH_MUTED, size=9),
                ),
                bar=dict(color=COLOR_NEGATIVE if pct > 100 else COLOR_POSITIVE, thickness=0.55),
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
                steps=[
                    dict(range=[0, 100], color="rgba(157,163,168,0.10)"),
                    dict(range=[100, 150], color="rgba(214,32,63,0.12)"),
                ],
                threshold=dict(line=dict(color=COLOR_DASH_FG, width=3), thickness=0.8, value=100),
            ),
        )
    )
    fig.update_layout(
        height=220,
        margin=dict(l=18, r=18, t=12, b=6),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLOR_DASH_FG, family=DASH_FONT),
    )
    return fig


def _kpi_card(
    caption: str,
    value: str,
    accent: str,
    *,
    idx: int = 0,
    value_class: str = "",
    kpi_id: str = "",
    target: float | None = None,
    fmt: str = "",
    prefix: str = "",
    suffix: str = "",
) -> str:
    """One KPI tile. ``target``/``fmt`` drive the JS count-up; ``kpi_id`` lets the
    department filter recompute the value live."""
    data = ""
    if target is not None:
        data = f' data-target="{target}" data-format="{fmt}"'
        if prefix:
            data += f' data-prefix="{prefix}"'
        if suffix:
            data += f' data-suffix="{suffix}"'
    id_attr = f' id="kpi-{kpi_id}"' if kpi_id else ""
    return (
        f'<div class="kpi hud reveal" style="--i:{idx};border-top-color:{accent}">'
        f'<div class="tag">{idx + 1:02d}</div>'
        f'<div class="cap">{caption}</div>'
        f'<div class="val {value_class}"{id_attr}{data}>{value}</div></div>'
    )


def _tabs(chart: str, options: list[tuple[str, str, bool]]) -> str:
    """A glowing segmented control of view toggles for a chart card."""
    btns = "".join(
        f'<button class="tab{" on" if active else ""}" data-view="{view}">{label}</button>'
        for view, label, active in options
    )
    return f'<div class="tabs" data-chart="{chart}">{btns}</div>'


def _details_table(details: list[dict[str, Any]]) -> str:
    """Render an opportunity's flagged rows as a compact HUD table (first 12 rows)."""
    if not details:
        return '<div class="more">No line-item detail available.</div>'
    cols = list(details[0].keys())
    head = "".join(f"<th>{c}</th>" for c in cols)
    rows = []
    for record in details[:12]:
        cells = []
        for col in cols:
            value = record[col]
            if col in ("Variance", "Actual Amount") and isinstance(value, (int, float)):
                cells.append(f'<td class="num">{compact_money(float(value))}</td>')
            elif col == "Date":
                cells.append(f"<td>{pd.to_datetime(value).strftime('%d %b %Y')}</td>")
            else:
                cells.append(f"<td>{value}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    more = "" if len(details) <= 12 else f'<div class="more">+ {len(details) - 12} more…</div>'
    return f"<table><thead><tr>{head}</tr></thead>" f"<tbody>{''.join(rows)}</tbody></table>{more}"


def _data_payload(
    dept_summary: pd.DataFrame,
    monthly_trend: pd.DataFrame,
    kpis: KpiSummary,
    df: pd.DataFrame | None,
) -> str:
    """Embed everything the JS controller needs to re-render charts and recompute KPIs.

    When ``df`` is provided we also embed a month×department matrix so the department
    filter can recompute the monthly trend; without it the filter falls back to the
    unfiltered monthly totals.
    """
    counts: dict[Any, int] = df.groupby("Department").size().to_dict() if df is not None else {}
    depts: list[dict[str, Any]] = []
    for _, row in dept_summary.iterrows():
        name = str(row["Department"])
        entry: dict[str, Any] = {
            "name": name,
            "budget": float(row["Budgeted Amount"]),
            "actual": float(row["Actual Amount"]),
            "variance": float(row["Variance"]),
        }
        if df is not None:
            entry["count"] = int(counts.get(name, 0))
        depts.append(entry)

    month_actual: dict[str, list[float]] = {}
    month_budget: dict[str, list[float]] = {}
    if df is not None:
        mdf = df.assign(_m=pd.to_datetime(df["Date"]).dt.month)
        cols = range(1, 13)
        pa = mdf.pivot_table(
            index="Department", columns="_m", values="Actual Amount", aggfunc="sum", fill_value=0.0
        ).reindex(columns=cols, fill_value=0.0)
        pb = mdf.pivot_table(
            index="Department",
            columns="_m",
            values="Budgeted Amount",
            aggfunc="sum",
            fill_value=0.0,
        ).reindex(columns=cols, fill_value=0.0)
        month_actual = {str(i): [float(v) for v in r] for i, r in pa.iterrows()}
        month_budget = {str(i): [float(v) for v in r] for i, r in pb.iterrows()}

    payload = {
        "hasTx": df is not None,
        "totalDepts": int(len(dept_summary)),
        "depts": depts,
        "months": [str(m) for m in monthly_trend["Month Name"]],
        "monthActual": month_actual,
        "monthBudget": month_budget,
        "monthActualTotal": [float(v) for v in monthly_trend["Actual Amount"]],
        "monthBudgetTotal": [float(v) for v in monthly_trend["Budgeted Amount"]],
        "palette": list(_DEPT_PALETTE),
        "font": DASH_FONT,
        "colors": {
            "blue": COLOR_DASH_TITANIUM,  # Budget series
            "red": COLOR_DASH_CRIMSON,  # Actual series
            "pos": COLOR_POSITIVE,
            "neg": COLOR_NEGATIVE,
            "fg": COLOR_DASH_FG,
            "muted": COLOR_DASH_MUTED,
            "grid": COLOR_DASH_GRID,
            "surface": COLOR_DASH_SURFACE,
            "bg": COLOR_DASH_BG,
        },
    }
    return json.dumps(payload)


_CSS = Template("""
* { box-sizing: border-box; }
body { margin: 0; color: $FG; font-family: $FONT; -webkit-font-smoothing: antialiased;
       text-rendering: optimizeLegibility; background-color: $BG;
       background-image:
         radial-gradient(140% 110% at 50% 38%, transparent 55%, rgba(0,0,0,.6) 100%),
         radial-gradient(1200px 480px at 50% -10%, rgba(179,18,43,.16), transparent 70%),
         linear-gradient(rgba(179,18,43,.035) 1px, transparent 1px),
         linear-gradient(90deg, rgba(179,18,43,.035) 1px, transparent 1px);
       background-size: auto, auto, 44px 44px, 44px 44px;
       background-attachment: fixed; }
::selection { background: rgba(214,32,63,.45); color: $FG; }
.wrap { max-width: 1480px; margin: 0 auto; padding: 28px 24px 52px; position: relative; z-index: 1; }
/* HUD corner brackets — thin crimson L's at opposite corners */
.hud { position: relative; }
.hud::before, .hud::after { content: ""; position: absolute; width: 16px; height: 16px;
       border: 1.5px solid $BLUE; pointer-events: none;
       filter: drop-shadow(0 0 4px rgba(179,18,43,.75));
       transition: top .22s ease, left .22s ease, right .22s ease, bottom .22s ease,
                   border-color .22s ease; }
.hud::before { top: 9px; left: 9px; border-right: 0; border-bottom: 0; border-top-left-radius: 4px; }
.hud::after { bottom: 9px; right: 9px; border-left: 0; border-top: 0; border-bottom-right-radius: 4px; }
/* Lock-on: brackets snap toward the corners and brighten on hover */
.hud:hover::before { top: 5px; left: 5px; border-color: $NEON; }
.hud:hover::after { bottom: 5px; right: 5px; border-color: $NEON; }

/* Animated background field: scanline sweep + breathing glow + film grain */
.fx { position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden; }
.fx .grain { position: absolute; inset: 0; opacity: .05; mix-blend-mode: overlay;
             background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"); }
.fx .scan { position: absolute; left: 0; right: 0; height: 160px; top: -160px;
            background: linear-gradient(180deg, transparent, $SCAN, transparent);
            animation: scan 7.5s linear infinite; }
@keyframes scan { 0% { top: -160px; } 100% { top: 100%; } }
.fx .pulse { position: absolute; top: -12%; left: 50%; width: 1200px; height: 520px;
             transform: translateX(-50%);
             background: radial-gradient(closest-side, rgba(179,18,43,.16), transparent 70%);
             animation: breathe 6s ease-in-out infinite; }
@keyframes breathe { 0%,100% { opacity: .5; } 50% { opacity: 1; } }

/* Entrance reveal (staggered) */
.reveal { opacity: 0; transform: translateY(18px);
          transition: opacity .6s cubic-bezier(.2,.7,.2,1), transform .6s cubic-bezier(.2,.7,.2,1);
          transition-delay: calc(var(--i,0) * 55ms); }
.reveal.in { opacity: 1; transform: none; }

.banner { display: flex; align-items: center; justify-content: space-between; gap: 18px;
          background:
            repeating-linear-gradient(-45deg, rgba(236,229,213,.016) 0 2px, transparent 2px 6px),
            linear-gradient(135deg, $CHARCOAL, #0C0D0F);
          border: 1px solid rgba(236,229,213,.09);
          border-radius: 18px; padding: 22px 28px;
          box-shadow: 0 12px 34px rgba(0,0,0,.40), inset 0 1px 0 rgba(236,229,213,.06),
                      inset 0 0 0 1px rgba(179,18,43,.14), 0 0 38px rgba(179,18,43,.10); }
.banner .title { font-size: 27px; font-weight: 800; letter-spacing: .04em; position: relative;
                 overflow: hidden; text-shadow: 0 0 22px rgba(179,18,43,.30); }
.banner .title::after { content: ""; position: absolute; top: 0; left: -60%; width: 55%; height: 100%;
                 background: linear-gradient(90deg, transparent, rgba(236,229,213,.30), transparent);
                 transform: skewX(-20deg); animation: sweep 5.5s ease-in-out infinite; }
@keyframes sweep { 0%,14% { left: -60%; } 55%,100% { left: 135%; } }
.banner .sub { color: $MUTED; font-size: 13px; margin-top: 6px; letter-spacing: .02em; }
.right { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }
.live { display: inline-flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 700;
        letter-spacing: .24em; text-transform: uppercase; color: $BLUE; }
.live .dot { width: 8px; height: 8px; border-radius: 50%; background: $BLUE;
             box-shadow: 0 0 8px $BLUE, 0 0 16px $BLUE; animation: blink 1.6s ease-in-out infinite; }
@keyframes blink { 0%,100% { opacity: 1; box-shadow: 0 0 8px $BLUE, 0 0 16px rgba(179,18,43,.6); }
                   50% { opacity: .45; box-shadow: 0 0 4px rgba(179,18,43,.4); } }
.badge { font-size: 26px; font-weight: 800; color: $FG; letter-spacing: .04em;
         border: 1px solid $CRIMSON; border-radius: 12px; padding: 10px 16px;
         background: rgba(179,18,43,.08); box-shadow: 0 0 20px rgba(179,18,43,.14); }
/* Banner telemetry readout: system status + live UTC clock */
.tele { display: inline-flex; align-items: center; gap: 9px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px;
        letter-spacing: .14em; color: $MUTED; }
.tele .ok { color: $POS; }
.tele .sep { color: rgba(236,229,213,.22); }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 22px 0; }
.kpi { background: linear-gradient(180deg, rgba(43,46,51,.48), rgba(10,11,13,.82));
       backdrop-filter: blur(12px) saturate(1.15);
       -webkit-backdrop-filter: blur(12px) saturate(1.15);
       border: 1px solid rgba(236,229,213,.08); border-top: 3px solid $BLUE;
       border-radius: 14px; padding: 18px 20px 20px 22px;
       box-shadow: 0 6px 18px rgba(0,0,0,.28), inset 0 1px 0 rgba(236,229,213,.05),
                   0 0 0 1px rgba(179,18,43,.05);
       transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }
.kpi:hover { transform: translateY(-3px); border-color: rgba(236,229,213,.14);
             box-shadow: 0 12px 26px rgba(0,0,0,.34), 0 0 24px rgba(179,18,43,.20); }
.kpi .cap { font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase; color: $MUTED; }
.kpi .tag { position: absolute; top: 10px; right: 13px; font-size: 9px; letter-spacing: .16em;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            color: rgba(236,229,213,.20); }
.kpi .val { font-size: 34px; font-weight: 800; margin-top: 10px; line-height: 1.08;
            letter-spacing: -.015em; font-variant-numeric: tabular-nums;
            text-shadow: 0 0 18px $GLOW; }
.pos { color: $POS; text-shadow: 0 0 18px rgba(157,163,168,.42); }
.neg { color: $NEG; text-shadow: 0 0 18px rgba(214,32,63,.42); }

/* Vitals strip: utilisation gauge + best/worst callouts */
.vitals { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 2px 0 4px; }
.callouts { display: grid; grid-template-rows: 1fr 1fr; gap: 16px; }
.callout { display: flex; align-items: center; justify-content: space-between; gap: 12px;
           border: 1px solid rgba(236,229,213,.08); border-radius: 14px; padding: 16px 20px;
           background: linear-gradient(180deg, rgba(43,46,51,.42), rgba(8,9,11,.78));
           backdrop-filter: blur(12px) saturate(1.15);
           -webkit-backdrop-filter: blur(12px) saturate(1.15);
           box-shadow: 0 6px 18px rgba(0,0,0,.28), inset 0 1px 0 rgba(236,229,213,.05),
                       0 0 0 1px rgba(179,18,43,.05); }
.callout .lab { font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase; color: $MUTED; }
.callout .dn { font-size: 19px; font-weight: 800; margin-top: 5px; }
.callout .cv { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; }
.callout.best { border-left: 4px solid $POS; }
.callout.worst { border-left: 4px solid $NEG; }

/* Department filter chips */
.filterbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin: 22px 2px 8px; }
.flabel { font-size: 11px; letter-spacing: .18em; text-transform: uppercase; color: $MUTED;
          margin-right: 2px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 7px; cursor: pointer; font-size: 12px;
        font-weight: 600; color: $MUTED; letter-spacing: .02em;
        background: rgba(179,18,43,.06); border: 1px solid $GRID; border-radius: 999px;
        padding: 6px 12px; transition: color .16s ease, border-color .16s ease,
        background .16s ease, box-shadow .16s ease; }
.chip .cdot { width: 8px; height: 8px; border-radius: 50%; opacity: .4; transition: opacity .16s ease; }
.chip.on { color: $FG; border-color: $NEON; background: rgba(179,18,43,.16);
           box-shadow: 0 0 14px rgba(214,32,63,.25); }
.chip.on .cdot { opacity: 1; box-shadow: 0 0 8px currentColor; }
.chip:hover { border-color: $NEON; }
.chipbtn { cursor: pointer; font-size: 10.5px; letter-spacing: .14em; text-transform: uppercase;
           font-weight: 700; color: $MUTED; background: transparent; border: 1px solid $GRID;
           border-radius: 8px; padding: 6px 10px; transition: color .15s ease, border-color .15s ease; }
.chipbtn:hover { color: $FG; border-color: $NEON; }

.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
/* Arc-reactor rings orbiting inside the donut hole (centred on the hole at 33%/50%,
   matching the pie domain x=[0,0.66] and its centre annotation) */
.mixwrap { position: relative; }
.mixwrap .ring { position: absolute; top: 50%; left: 33%; border-radius: 50%;
                 pointer-events: none; transform: translate(-50%,-50%); }
.mixwrap .r1 { width: 142px; height: 142px; border: 1px dashed rgba(214,32,63,.30);
               animation: orbit 40s linear infinite; }
.mixwrap .r2 { width: 160px; height: 160px; border: 1px solid rgba(236,229,213,.07);
               border-top-color: rgba(214,32,63,.50); border-right-color: rgba(214,32,63,.16);
               animation: orbitrev 12s linear infinite; }
@keyframes orbit { to { transform: translate(-50%,-50%) rotate(360deg); } }
@keyframes orbitrev { to { transform: translate(-50%,-50%) rotate(-360deg); } }
.card { background: linear-gradient(180deg, rgba(43,46,51,.42), rgba(8,9,11,.78));
        backdrop-filter: blur(12px) saturate(1.15);
        -webkit-backdrop-filter: blur(12px) saturate(1.15);
        border: 1px solid rgba(236,229,213,.08); border-radius: 16px; padding: 16px 16px 8px;
        box-shadow: 0 6px 18px rgba(0,0,0,.28), inset 0 1px 0 rgba(236,229,213,.05),
                    0 0 0 1px rgba(179,18,43,.05);
        margin-bottom: 16px; transition: box-shadow .18s ease, border-color .18s ease; }
.card:hover { border-color: rgba(236,229,213,.13);
              box-shadow: 0 10px 24px rgba(0,0,0,.32), 0 0 24px rgba(179,18,43,.14); }
.cardhead { display: flex; align-items: center; justify-content: space-between;
            margin: 6px 6px 0 20px; gap: 12px; padding-bottom: 10px;
            border-bottom: 1px solid rgba(236,229,213,.06); }
.cardhead h3 { margin: 0; font-size: 14px; font-weight: 700; letter-spacing: .05em;
               text-transform: uppercase; color: $FG; }

/* Per-chart view tabs */
.tabs { display: inline-flex; gap: 2px; background: rgba(179,18,43,.08); border: 1px solid $GRID;
        border-radius: 9px; padding: 3px; }
.tab { cursor: pointer; font-size: 11px; font-weight: 700; letter-spacing: .04em; color: $MUTED;
       background: transparent; border: 0; border-radius: 6px; padding: 5px 11px;
       transition: color .15s ease, background .15s ease, box-shadow .15s ease; }
.tab.on { color: $FG; background: linear-gradient(180deg, rgba(214,32,63,.40), rgba(179,18,43,.28));
          box-shadow: 0 0 12px rgba(214,32,63,.32); }

.section { font-size: 13px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase;
           margin: 26px 4px 14px; color: $FG; display: flex; align-items: center; gap: 10px; }
.section::before { content: ""; width: 22px; height: 2px; background: $BLUE; border-radius: 2px;
                   box-shadow: 0 0 10px $BLUE; }
.section::after { content: ""; flex: 1; height: 1px;
                  background: linear-gradient(90deg, rgba(179,18,43,.35), transparent); }
.savings { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; align-items: start; }
.save { background: linear-gradient(180deg, rgba(43,46,51,.42), rgba(8,9,11,.78));
        backdrop-filter: blur(12px) saturate(1.15);
        -webkit-backdrop-filter: blur(12px) saturate(1.15);
        border: 1px solid rgba(236,229,213,.08); border-left: 4px solid $POS;
        border-radius: 14px; padding: 16px 18px; position: relative;
        box-shadow: 0 6px 18px rgba(0,0,0,.28), inset 0 1px 0 rgba(236,229,213,.05),
                    0 0 0 1px rgba(179,18,43,.05);
        transition: box-shadow .18s ease; }
.save[data-drill] { cursor: pointer; }
.save[data-drill]:hover { box-shadow: 0 10px 24px rgba(0,0,0,.32), 0 0 22px rgba(157,163,168,.16); }
.saveclick { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.save .t { font-weight: 700; font-size: 15px; }
.save .n { color: $MUTED; font-size: 12px; margin-top: 4px; }
.save .amt { font-size: 24px; font-weight: 800; color: $POS; white-space: nowrap;
             font-variant-numeric: tabular-nums; text-shadow: 0 0 16px rgba(157,163,168,.35); }
.save .chev { position: absolute; right: 16px; bottom: 12px; color: $MUTED; font-size: 13px;
              transition: transform .25s ease; }
.save.open .chev { transform: rotate(180deg); }
.drill { max-height: 0; opacity: 0; overflow: hidden;
         transition: max-height .35s ease, opacity .3s ease, margin-top .35s ease; }
.save.open .drill { max-height: 560px; opacity: 1; margin-top: 14px; }
.drill table { width: 100%; border-collapse: collapse; font-size: 11.5px; }
.drill th { text-align: left; color: $MUTED; font-weight: 600; letter-spacing: .04em;
            text-transform: uppercase; font-size: 10px; padding: 6px 8px; border-bottom: 1px solid $GRID; }
.drill td { padding: 6px 8px; border-bottom: 1px solid rgba(236,229,213,.06); color: $FG; }
.drill td.num { font-variant-numeric: tabular-nums; text-align: right;
                font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.drill tbody tr:nth-child(even) td { background: rgba(236,229,213,.025); }
.drill tr:hover td { background: rgba(179,18,43,.10); }
.drill .more { color: $MUTED; font-size: 11px; padding: 6px 8px; }

@media (max-width: 980px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .vitals { grid-template-columns: 1fr; }
  .grid2 { grid-template-columns: 1fr; }
  .savings { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .mixwrap .ring { display: none; }  /* the donut hole shrinks below the ring diameter */
}
@media (prefers-reduced-motion: reduce) {
  .reveal { opacity: 1 !important; transform: none !important; transition: none !important; }
  .fx .scan, .fx .pulse, .banner .title::after, .live .dot,
  .mixwrap .ring { animation: none !important; }
}
""")


# Vanilla-JS controller. Plain string (NOT a Template) so JS braces pass through untouched;
# all data crosses the boundary via the JSON <script id="opex-data"> payload.
_JS = """
(function () {
  var data = JSON.parse(document.getElementById('opex-data').textContent);
  var C = data.colors;
  var cfg = { displayModeBar: false, responsive: true };
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var active = new Set(data.depts.map(function (d) { return d.name; }));
  var views = { budget: 'abs', variance: 'abs', monthly: 'monthly' };
  var mixSeen = false;
  var mixTotal = data.depts.reduce(function (s, d) { return s + d.actual; }, 0);
  // Stable department→colour map (actual-spend rank) — mirrors _dept_color_map so a
  // department keeps its colour across filters and matches its chip dot.
  var deptColor = {};
  data.depts.slice().sort(function (a, b) { return b.actual - a.actual; })
    .forEach(function (d, i) { deptColor[d.name] = data.palette[i % data.palette.length]; });

  function compactMoney(v) {
    var a = Math.abs(v);
    if (a >= 1e6) return '$' + (v / 1e6).toFixed(1) + 'M';
    if (a >= 1e3) return '$' + Math.round(v / 1e3).toLocaleString() + 'K';
    return '$' + Math.round(v).toLocaleString();
  }
  function fmtVal(v, fmt) {
    if (fmt === 'money') return compactMoney(v);
    if (fmt === 'pct1') return v.toFixed(1) + '%';
    return Math.round(v).toLocaleString();
  }

  // KPI count-up
  function animateValue(el, to) {
    var fmt = el.dataset.format || 'int';
    var prefix = el.dataset.prefix ? el.dataset.prefix + ' ' : '';
    var suffix = el.dataset.suffix ? ' ' + el.dataset.suffix : '';
    el.dataset.target = to;
    if (reduce) { el.dataset.cur = to; el.textContent = prefix + fmtVal(to, fmt) + suffix; return; }
    var from = parseFloat(el.dataset.cur || '0');
    var t0 = performance.now(), dur = 1000;
    function step(t) {
      var p = Math.min(1, (t - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      el.textContent = prefix + fmtVal(from + (to - from) * e, fmt) + suffix;
      if (p < 1) requestAnimationFrame(step); else el.dataset.cur = to;
    }
    requestAnimationFrame(step);
  }

  function activeRows() {
    return data.depts.filter(function (d) { return active.has(d.name); });
  }

  // HUD text decode: scramble glyphs resolve left-to-right into the real title.
  function decode(el) {
    var fin = el.textContent;
    if (reduce || !fin) return;
    var glyphs = '<>/\\|=+*#%&0123456789ABCDEF';
    var t0 = performance.now(), dur = 650;
    function step(t) {
      var p = Math.min(1, (t - t0) / dur);
      var n = Math.floor(p * fin.length);
      var out = fin.slice(0, n);
      for (var i = n; i < fin.length; i++) {
        out += fin[i] === ' ' ? ' ' : glyphs[(Math.random() * glyphs.length) | 0];
      }
      el.textContent = out;
      if (p < 1) requestAnimationFrame(step); else el.textContent = fin;
    }
    requestAnimationFrame(step);
  }

  // Banner telemetry clock
  function tickClock() {
    var el = document.getElementById('hud-clock');
    if (!el) return;
    function f() { el.textContent = new Date().toISOString().slice(11, 19) + ' UTC'; }
    f(); setInterval(f, 1000);
  }

  // Plotly styling helpers (mirror the server-side _style)
  function axisStyle(extra) {
    return Object.assign({
      gridcolor: 'rgba(236,229,213,0.07)', griddash: 'dot', gridwidth: 1,
      zerolinecolor: 'rgba(236,229,213,0.18)', linecolor: C.grid, color: C.muted,
      ticklabelstandoff: 6
    }, extra || {});
  }
  function baseLayout(extra) {
    return Object.assign({
      margin: { l: 12, r: 18, t: 8, b: 8 },
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: C.fg, family: data.font, size: 12 },
      hoverlabel: { bgcolor: C.surface, bordercolor: 'rgba(236,229,213,0.18)',
                    font: { size: 12, family: data.font, color: C.fg } },
      legend: { orientation: 'h', yanchor: 'bottom', y: 1.0, x: 0, bgcolor: 'rgba(0,0,0,0)' },
      transition: { duration: 500, easing: 'cubic-in-out' },
      xaxis: axisStyle(), yaxis: axisStyle()
    }, extra || {});
  }
  // Magnitude-graded fills (mirror the server-side _grade_alpha)
  function gradeColor(v, maxAbs) {
    var a = maxAbs > 0 ? 0.45 + 0.55 * Math.abs(v) / maxAbs : 1;
    return (v > 0 ? 'rgba(214,32,63,' : 'rgba(157,163,168,') + a.toFixed(2) + ')';
  }

  function buildBudget() {
    var rows = activeRows();
    var x = rows.map(function (d) { return d.name; });
    if (views.budget === 'pct') {
      // Utilisation view: actual as % of budget, graded by distance from the 100% line.
      // (Variance % already has its own chart — this view answers a different question.)
      var y = rows.map(function (d) { return d.budget ? d.actual / d.budget * 100 : 0; });
      var dev = y.map(function (v) { return v - 100; });
      var mx = Math.max.apply(null, dev.map(Math.abs).concat([0]));
      var col = dev.map(function (v) { return gradeColor(v, mx); });
      return { data: [{ type: 'bar', x: x, y: y, marker: { color: col, line: { width: 0 } },
                 hovertemplate: '%{x}<br>%{y:.1f}% of budget<extra></extra>' }],
        layout: baseLayout({ showlegend: false, bargap: 0.34, barcornerradius: 4,
                 shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 100, y1: 100,
                   line: { color: 'rgba(236,229,213,0.35)', width: 1, dash: 'dash' } }],
                 xaxis: axisStyle({ tickangle: -30 }), yaxis: axisStyle({ ticksuffix: '%' }) }) };
    }
    return { data: [
      { type: 'bar', name: 'Budget', x: x, y: rows.map(function (d) { return d.budget; }),
        marker: { color: C.blue, opacity: 0.92, line: { width: 0 } },
        hovertemplate: 'Budget  $%{y:,.0f}<extra></extra>' },
      { type: 'bar', name: 'Actual', x: x, y: rows.map(function (d) { return d.actual; }),
        marker: { color: C.red, line: { width: 0 } },
        hovertemplate: 'Actual  $%{y:,.0f}<extra></extra>' }],
      layout: baseLayout({ barmode: 'group', bargap: 0.34, bargroupgap: 0.08,
        barcornerradius: 4, hovermode: 'x unified',
        xaxis: axisStyle({ tickangle: -30 }), yaxis: axisStyle({ tickprefix: '$', tickformat: '~s' }) }) };
  }

  function mixCenterHtml(big, small) {
    return '<b>' + big + '</b><br>' +
      '<span style="font-size:11px;color:' + C.muted + '">' + small + '</span>';
  }

  function buildMix() {
    var rows = activeRows().slice().sort(function (a, b) { return b.actual - a.actual; });
    mixTotal = rows.reduce(function (s, d) { return s + d.actual; }, 0);
    return { data: [{ type: 'pie', labels: rows.map(function (d) { return d.name; }),
        values: rows.map(function (d) { return d.actual; }), hole: 0.62, sort: false,
        direction: 'clockwise',
        marker: { colors: rows.map(function (d) { return deptColor[d.name]; }),
                  line: { color: C.bg, width: 3 } },
        textinfo: 'percent', textfont: { size: 11, family: data.font },
        insidetextorientation: 'horizontal', domain: { x: [0, 0.66] },
        hovertemplate: '%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>' }],
      layout: baseLayout({ legend: { orientation: 'v', x: 0.72, y: 0.5, font: { size: 11 } },
        annotations: [{ text: mixCenterHtml(compactMoney(mixTotal), 'Actual spend'),
          x: 0.33, y: 0.5, xref: 'paper', yref: 'paper', showarrow: false,
          font: { size: 19, color: C.fg } }] }) };
  }

  function monthSeries(which) {
    if (!data.hasTx) return which === 'actual' ? data.monthActualTotal : data.monthBudgetTotal;
    var m = which === 'actual' ? data.monthActual : data.monthBudget;
    return data.months.map(function (_, i) {
      var s = 0;
      for (var k in m) { if (active.has(k)) s += m[k][i]; }
      return s;
    });
  }
  function cumsum(arr) { var t = 0; return arr.map(function (v) { return (t += v); }); }

  function buildMonthly() {
    var act = monthSeries('actual'), bud = monthSeries('budget');
    if (views.monthly === 'cumulative') { act = cumsum(act); bud = cumsum(bud); }
    return { data: [
      { type: 'scatter', name: 'Budget', x: data.months, y: bud, mode: 'lines+markers',
        line: { color: C.blue, width: 2.5, shape: 'spline', smoothing: 0.75 },
        marker: { size: 6, line: { color: C.bg, width: 1.5 } },
        hovertemplate: 'Budget  $%{y:,.0f}<extra></extra>' },
      { type: 'scatter', name: 'Actual', x: data.months, y: act, mode: 'lines+markers',
        line: { color: C.red, width: 3, shape: 'spline', smoothing: 0.75 },
        marker: { size: 7, line: { color: C.bg, width: 1.5 } }, fill: 'tozeroy',
        fillcolor: 'rgba(179,18,43,0.10)', hovertemplate: 'Actual  $%{y:,.0f}<extra></extra>' }],
      layout: baseLayout({ hovermode: 'x unified',
        yaxis: axisStyle({ tickprefix: '$', tickformat: '~s' }) }) };
  }

  function buildVariance() {
    var pct = views.variance === 'pct';
    var valOf = pct ? function (d) { return d.budget ? d.variance / d.budget * 100 : 0; }
                    : function (d) { return d.variance; };
    var rows = activeRows().slice().sort(function (a, b) { return valOf(a) - valOf(b); });
    var y = rows.map(function (d) { return d.name; });
    var x = rows.map(valOf);
    var mx = Math.max.apply(null, x.map(Math.abs).concat([0]));
    var col = x.map(function (v) { return gradeColor(v, mx); });
    var text = pct ? x.map(function (v) { return v.toFixed(1) + '%'; })
                   : x.map(function (v) { return compactMoney(v); });
    var vmax = Math.max.apply(null, x.concat([0]));
    var vmin = Math.min.apply(null, x.concat([0]));
    var pad = ((vmax - vmin) * 0.18) || 1;
    var xa = axisStyle({ zeroline: true, zerolinewidth: 2, zerolinecolor: C.muted,
                         range: [vmin - pad, vmax + pad] });
    if (pct) { xa.ticksuffix = '%'; } else { xa.tickprefix = '$'; xa.tickformat = '~s'; }
    return { data: [{ type: 'bar', orientation: 'h', y: y, x: x,
        marker: { color: col, line: { width: 0 } },
        text: text, textposition: 'outside', cliponaxis: false,
        textfont: { size: 11, family: data.font },
        hovertemplate: pct ? '%{y}<br>Variance %{x:.1f}%<extra></extra>'
                           : '%{y}<br>Variance $%{x:,.0f}<extra></extra>' }],
      layout: baseLayout({ showlegend: false, bargap: 0.32, barcornerradius: 3,
        margin: { l: 12, r: 64, t: 8, b: 8 }, xaxis: xa, yaxis: axisStyle() }) };
  }

  function buildGauge() {
    var rows = activeRows();
    var bud = rows.reduce(function (s, d) { return s + d.budget; }, 0);
    var act = rows.reduce(function (s, d) { return s + d.actual; }, 0);
    var pct = bud ? act / bud * 100 : 0;
    return { data: [{ type: 'indicator', mode: 'gauge+number+delta', value: pct,
        number: { suffix: '%', font: { size: 34, color: C.fg, family: data.font } },
        delta: { reference: 100, suffix: '%', font: { size: 13 },
          increasing: { color: C.neg }, decreasing: { color: C.pos } },
        gauge: { axis: { range: [0, 150], tickcolor: 'rgba(236,229,213,0.25)', ticksuffix: '%',
            tickfont: { color: C.muted, size: 9 } },
          bar: { color: pct > 100 ? C.neg : C.pos, thickness: 0.55 },
          bgcolor: 'rgba(0,0,0,0)', borderwidth: 0,
          steps: [{ range: [0, 100], color: 'rgba(157,163,168,0.10)' },
                  { range: [100, 150], color: 'rgba(214,32,63,0.12)' }],
          threshold: { line: { color: C.fg, width: 3 }, thickness: 0.8, value: 100 } } }],
      layout: { height: 220, margin: { l: 18, r: 18, t: 12, b: 6 }, paper_bgcolor: 'rgba(0,0,0,0)',
        font: { color: C.fg, family: data.font } } };
  }

  function draw(id, spec) {
    if (window.Plotly) Plotly.react(id, spec.data, spec.layout, cfg);
  }

  // Donut motion: slices rest flush; the highlight is earned by interaction.
  // sweepMix spins the ring in on reveal/redraw, setPull eases the hovered
  // slice outward, and the centre readout swaps to the hovered department.
  function sweepMix(dur) {
    var gd = document.getElementById('fig-mix');
    if (!gd || !window.Plotly || reduce) return;
    var t0 = performance.now();
    function step(t) {
      var p = Math.min(1, (t - t0) / dur);
      var e = 1 - Math.pow(1 - p, 3);
      Plotly.restyle(gd, { rotation: -120 * (1 - e), opacity: 0.15 + 0.85 * e }, [0]);
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  function setPull(gd, target) {
    if (gd._mixRaf) cancelAnimationFrame(gd._mixRaf);
    if (reduce) { Plotly.restyle(gd, { pull: [target] }, [0]); gd._mixPull = target; return; }
    var start = gd._mixPull || [];
    var t0 = performance.now(), dur = 260;
    function step(t) {
      var p = Math.min(1, (t - t0) / dur);
      var e = 1 - Math.pow(1 - p, 2);
      var cur = target.map(function (v, i) { return (start[i] || 0) + (v - (start[i] || 0)) * e; });
      Plotly.restyle(gd, { pull: [cur] }, [0]);
      gd._mixPull = cur;
      if (p < 1) gd._mixRaf = requestAnimationFrame(step);
    }
    gd._mixRaf = requestAnimationFrame(step);
  }
  function wireMixFx() {
    var gd = document.getElementById('fig-mix');
    if (!gd || !window.Plotly) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting && !mixSeen) { mixSeen = true; sweepMix(900); io.disconnect(); }
      });
    }, { threshold: 0.35 });
    io.observe(gd);
    if (!gd.on) return;
    // A small pull plus a grace delay on retract keeps the slice from
    // oscillating when its geometry shifts underneath the cursor.
    var hoverIdx = -1, unhoverT = 0;
    gd.on('plotly_hover', function (ev) {
      var pt = ev.points && ev.points[0];
      if (!pt || pt.data.type !== 'pie') return;
      clearTimeout(unhoverT);
      if (pt.pointNumber === hoverIdx) return;
      hoverIdx = pt.pointNumber;
      var vals = pt.data.values, tot = 0, i;
      for (i = 0; i < vals.length; i++) tot += vals[i];
      var pull = vals.map(function (_, j) { return j === hoverIdx ? 0.03 : 0; });
      setPull(gd, pull);
      Plotly.relayout(gd, { 'annotations[0].text': mixCenterHtml(
        compactMoney(vals[hoverIdx]),
        pt.label + '<br>' + (tot ? (vals[hoverIdx] / tot * 100).toFixed(1) : '0.0') + '%') });
    });
    gd.on('plotly_unhover', function () {
      clearTimeout(unhoverT);
      unhoverT = setTimeout(function () {
        hoverIdx = -1;
        setPull(gd, (gd.data[0].values || []).map(function () { return 0; }));
        Plotly.relayout(gd, { 'annotations[0].text':
          mixCenterHtml(compactMoney(mixTotal), 'Actual spend') });
      }, 140);
    });
  }
  function drawMix() {
    var gd = document.getElementById('fig-mix');
    if (gd) { gd._mixPull = null; }
    draw('fig-mix', buildMix());
    if (mixSeen) sweepMix(600);
  }

  function drawAll() {
    draw('fig-budget', buildBudget()); drawMix();
    draw('fig-monthly', buildMonthly()); draw('fig-variance', buildVariance());
    draw('fig-gauge', buildGauge());
  }

  // KPI recompute from the visible department subset
  function kel(id) { return document.getElementById('kpi-' + id); }
  function setKpi(id, val) { var e = kel(id); if (e) animateValue(e, val); }
  function setSigned(id, val) {
    var e = kel(id); if (!e) return;
    var over = val > 0;
    e.dataset.prefix = over ? '▲' : '▼';
    e.className = 'val ' + (over ? 'neg' : 'pos');
    animateValue(e, Math.abs(val));
  }
  function recompute() {
    var rows = activeRows();
    var bud = rows.reduce(function (s, d) { return s + d.budget; }, 0);
    var act = rows.reduce(function (s, d) { return s + d.actual; }, 0);
    var over = rows.filter(function (d) { return d.variance > 0; }).length;
    setKpi('total_budget', bud);
    setKpi('total_actual', act);
    setSigned('total_variance', act - bud);
    setSigned('variance_pct', bud ? (act - bud) / bud * 100 : 0);
    var de = kel('departments_over_budget');
    if (de) { de.dataset.suffix = '/ ' + rows.length; de.className = 'val ' + (over ? 'neg' : 'pos');
              animateValue(de, over); }
    if (data.hasTx) {
      setKpi('transactions', rows.reduce(function (s, d) { return s + (d.count || 0); }, 0));
    }
  }

  function onFilter() { drawAll(); recompute(); }

  // Wiring
  function wire() {
    document.querySelectorAll('.chip').forEach(function (c) {
      c.addEventListener('click', function () {
        var d = c.dataset.dept;
        if (active.has(d)) { if (active.size > 1) { active.delete(d); c.classList.remove('on'); } }
        else { active.add(d); c.classList.add('on'); }
        onFilter();
      });
    });
    document.querySelectorAll('.chipbtn').forEach(function (b) {
      b.addEventListener('click', function () {
        if (b.dataset.act === 'all') { data.depts.forEach(function (d) { active.add(d.name); }); }
        else { active.clear(); active.add(data.depts[0].name); }
        document.querySelectorAll('.chip').forEach(function (c) {
          c.classList.toggle('on', active.has(c.dataset.dept));
        });
        onFilter();
      });
    });
    document.querySelectorAll('.tabs').forEach(function (g) {
      var chart = g.dataset.chart;
      g.querySelectorAll('.tab').forEach(function (t) {
        t.addEventListener('click', function () {
          g.querySelectorAll('.tab').forEach(function (x) { x.classList.remove('on'); });
          t.classList.add('on');
          views[chart] = t.dataset.view;
          if (chart === 'budget') draw('fig-budget', buildBudget());
          else if (chart === 'variance') draw('fig-variance', buildVariance());
          else if (chart === 'monthly') draw('fig-monthly', buildMonthly());
        });
      });
    });
    document.querySelectorAll('.save[data-drill]').forEach(function (s) {
      s.addEventListener('click', function () { s.classList.toggle('open'); });
    });

    wireMixFx();

    // Staggered entrance reveal; card/section titles decode as they come in.
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          var h = e.target.classList.contains('section')
            ? e.target : e.target.querySelector('.cardhead h3');
          if (h && !h.dataset.dec) { h.dataset.dec = '1'; decode(h); }
          io.unobserve(e.target);
        }
      });
    }, { threshold: 0.08 });
    document.querySelectorAll('.reveal').forEach(function (el) { io.observe(el); });

    var title = document.querySelector('.banner .title');
    if (title) decode(title);
    tickClock();

    // Count up every KPI from zero on load.
    document.querySelectorAll('.val[data-target]').forEach(function (e) {
      var to = parseFloat(e.dataset.target);
      if (reduce) { e.dataset.cur = to; }
      else { e.dataset.cur = 0; animateValue(e, to); }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
"""


def build_dashboard_html(
    dept_summary: pd.DataFrame,
    opportunities: list[Opportunity],
    monthly_trend: pd.DataFrame,
    kpis: KpiSummary,
    year: int,
    df: pd.DataFrame | None = None,
) -> str:
    """Assemble the full self-contained dashboard HTML document as a string.

    ``df`` is optional: when supplied (as ``write_dashboard`` always does), the department
    filter can also recompute the monthly trend and transaction count.
    """
    css = _CSS.substitute(
        BG=COLOR_DASH_BG,
        FG=COLOR_DASH_FG,
        FONT=DASH_FONT,
        GRID=COLOR_DASH_GRID,
        MUTED=COLOR_DASH_MUTED,
        SURFACE=COLOR_DASH_SURFACE,
        CHARCOAL=COLOR_DASH_CHARCOAL,
        BLUE=COLOR_DASH_CRIMSON,  # primary chrome accent
        CRIMSON=COLOR_DASH_CRIMSON,
        POS=COLOR_POSITIVE,
        NEG=COLOR_NEGATIVE,
        GLOW=COLOR_DASH_GLOW,
        NEON=COLOR_DASH_NEON,
        SCAN=COLOR_DASH_SCAN,
    )

    generated = datetime.now().strftime("%d %b %Y")
    banner = (
        '<div class="banner hud reveal"><div>'
        '<div class="title">RED BULL RACING &mdash; F1 OPEX</div>'
        f'<div class="sub">Operational expenditure cockpit &middot; FY{year} &middot; '
        f'{kpis["num_transactions"]:,} transactions &middot; generated {generated}</div>'
        '</div><div class="right">'
        '<div class="live"><span class="dot"></span>Live</div>'
        f'<div class="badge">FY{year}</div>'
        '<div class="tele"><span class="ok">SYS ONLINE</span><span class="sep">/</span>'
        '<span id="hud-clock">--:--:-- UTC</span></div></div></div>'
    )

    over = kpis["total_variance"] > 0
    arrow = "▲" if over else "▼"
    vcls = "neg" if over else "pos"
    depts_over = kpis["departments_over_budget"]
    total_depts = len(dept_summary)
    kpi_cards = "".join(
        [
            _kpi_card(
                "Total Budget",
                compact_money(kpis["total_budget"]),
                COLOR_DASH_CRIMSON,
                idx=0,
                kpi_id="total_budget",
                target=kpis["total_budget"],
                fmt="money",
            ),
            _kpi_card(
                "Total Actual",
                compact_money(kpis["total_actual"]),
                COLOR_DASH_CRIMSON,
                idx=1,
                kpi_id="total_actual",
                target=kpis["total_actual"],
                fmt="money",
            ),
            _kpi_card(
                "Total Variance",
                f'{arrow} {compact_money(abs(kpis["total_variance"]))}',
                COLOR_DASH_CRIMSON,
                idx=2,
                value_class=vcls,
                kpi_id="total_variance",
                target=abs(kpis["total_variance"]),
                fmt="money",
                prefix=arrow,
            ),
            _kpi_card(
                "Variance %",
                f'{arrow} {abs(kpis["variance_pct"]):.1%}',
                COLOR_DASH_CRIMSON,
                idx=3,
                value_class=vcls,
                kpi_id="variance_pct",
                target=abs(kpis["variance_pct"]) * 100,
                fmt="pct1",
                prefix=arrow,
            ),
            _kpi_card(
                "Potential Savings",
                compact_money(kpis["potential_savings"]),
                COLOR_POSITIVE,
                idx=4,
                kpi_id="potential_savings",
                target=kpis["potential_savings"],
                fmt="money",
            ),
            _kpi_card(
                "Opportunities",
                f'{kpis["num_opportunities"]}',
                COLOR_DASH_TAN,
                idx=5,
                kpi_id="num_opportunities",
                target=kpis["num_opportunities"],
                fmt="int",
            ),
            _kpi_card(
                "Depts Over Budget",
                f"{depts_over} / {total_depts}",
                COLOR_DASH_CRIMSON,
                idx=6,
                value_class="neg" if depts_over else "pos",
                kpi_id="departments_over_budget",
                target=depts_over,
                fmt="int",
                suffix=f"/ {total_depts}",
            ),
            _kpi_card(
                "Transactions",
                f'{kpis["num_transactions"]:,}',
                COLOR_DASH_TAN,
                idx=7,
                kpi_id="transactions",
                target=kpis["num_transactions"],
                fmt="int",
            ),
        ]
    )
    kpi_band = f'<div class="kpis">{kpi_cards}</div>'

    # Vitals strip: utilisation gauge + best/worst department callouts.
    # The gauge is the first figure in the document, so it inlines plotly.js once — every
    # later chart (and the JS controller's Plotly.react calls) then reuse that single copy.
    gauge_div = pio.to_html(
        _utilization_gauge_fig(kpis),
        full_html=False,
        include_plotlyjs="inline",
        config=_PLOTLY_CONFIG,
        div_id=_DIV_GAUGE,
    )
    ranked = dept_summary.sort_values("Variance")
    best, worst = ranked.iloc[0], ranked.iloc[-1]
    # Labels follow the sign so an all-over (or all-under) year never mislabels a callout.
    best_label = "Most Under Budget" if best["Variance"] < 0 else "Least Overspend"
    best_cls = "pos" if best["Variance"] < 0 else "neg"
    worst_label = "Biggest Overspend" if worst["Variance"] > 0 else "Closest to Budget"
    worst_cls = "neg" if worst["Variance"] > 0 else "pos"
    vitals_html = (
        '<div class="vitals">'
        '<div class="card hud reveal"><div class="cardhead">'
        "<h3>Budget Utilisation</h3></div>"
        f"{gauge_div}</div>"
        '<div class="callouts">'
        '<div class="callout best reveal"><div>'
        f'<div class="lab">{best_label}</div>'
        f'<div class="dn">{best["Department"]}</div></div>'
        f'<div class="cv {best_cls}">{compact_money(best["Variance"])}</div></div>'
        '<div class="callout worst reveal"><div>'
        f'<div class="lab">{worst_label}</div>'
        f'<div class="dn">{worst["Department"]}</div></div>'
        f'<div class="cv {worst_cls}">{compact_money(worst["Variance"])}</div></div>'
        "</div></div>"
    )

    charts = [
        ("Budget vs. Actual by Department", _budget_actual_fig(dept_summary), _DIV_BUDGET),
        ("Actual Spend Mix by Department", _spend_mix_fig(dept_summary), _DIV_MIX),
        ("Monthly Budget vs. Actual Spend", _monthly_trend_fig(monthly_trend), _DIV_MONTHLY),
        ("Department Variance vs. Budget", _variance_ranking_fig(dept_summary), _DIV_VARIANCE),
    ]
    divs = [
        pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs=False,  # plotly.js already inlined once by the gauge above
            config=_PLOTLY_CONFIG,
            div_id=div_id,
        )
        for _, fig, div_id in charts
    ]

    color_map = _dept_color_map(dept_summary)
    chips = "".join(
        f'<button class="chip on" data-dept="{dept}">'
        f'<span class="cdot" style="background:{color_map[str(dept)]}"></span>'
        f"{dept}</button>"
        for dept in dept_summary["Department"]
    )
    filterbar = (
        '<div class="filterbar reveal"><span class="flabel">Filter departments</span>'
        f'<div class="chips">{chips}</div>'
        '<button class="chipbtn" data-act="all">All</button>'
        '<button class="chipbtn" data-act="none">Solo</button></div>'
    )

    tabs_budget = _tabs("budget", [("abs", "$", True), ("pct", "% util", False)])
    tabs_variance = _tabs("variance", [("abs", "$", True), ("pct", "%", False)])
    tabs_monthly = _tabs(
        "monthly", [("monthly", "Monthly", True), ("cumulative", "Cumulative", False)]
    )

    def card(title: str, body: str, tabs: str = "") -> str:
        head = f'<div class="cardhead"><h3>{title}</h3>{tabs}</div>'
        return f'<div class="card hud reveal">{head}{body}</div>'

    mix_body = (
        f'<div class="mixwrap">{divs[1]}'
        '<div class="ring r1"></div><div class="ring r2"></div></div>'
    )
    charts_html = (
        f"{filterbar}"
        f'<div class="grid2">{card(charts[0][0], divs[0], tabs_budget)}'
        f"{card(charts[1][0], mix_body)}</div>"
        f"{card(charts[2][0], divs[2], tabs_monthly)}"
        f"{card(charts[3][0], divs[3], tabs_variance)}"
    )

    if opportunities:
        saves = "".join(
            '<div class="save hud reveal" data-drill>'
            f'<div class="saveclick"><div><div class="t">{opp["Type"]}</div>'
            f'<div class="n">{opp["Count"]} item(s) flagged &middot; click to inspect</div></div>'
            f'<div class="amt">{compact_money(opp["Potential Savings"])}</div></div>'
            '<div class="chev">&#9662;</div>'
            f'<div class="drill">{_details_table(opp["Details"])}</div></div>'
            for opp in opportunities
        )
        savings_html = (
            '<div class="section reveal">Identified Savings Opportunities</div>'
            f'<div class="savings">{saves}</div>'
        )
    else:
        savings_html = (
            '<div class="section reveal">Identified Savings Opportunities</div>'
            '<div class="save reveal"><div class="t">No opportunities flagged</div>'
            '<div class="n">All spending is within the configured detection thresholds.</div></div>'
        )

    payload = _data_payload(dept_summary, monthly_trend, kpis, df)
    scripts = (
        f'<script id="opex-data" type="application/json">{payload}</script>'
        f"<script>{_JS}</script>"
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Red Bull Racing &mdash; F1 OPEX Dashboard</title>"
        f"<style>{css}</style></head><body>"
        '<div class="fx"><div class="pulse"></div><div class="scan"></div>'
        '<div class="grain"></div></div>'
        '<div class="wrap">'
        f"{banner}{kpi_band}{vitals_html}{charts_html}{savings_html}"
        "</div>"
        f"{scripts}"
        "</body></html>"
    )


def write_dashboard(
    df: pd.DataFrame,
    dept_summary: pd.DataFrame,
    opportunities: list[Opportunity],
    monthly_trend: pd.DataFrame,
    kpis: KpiSummary,
    output_file: str = "f1opex_dashboard.html",
    year: int | None = None,
) -> None:
    """Build the interactive dashboard and write it to ``output_file`` as a single HTML file."""
    if dept_summary.empty:
        raise DashboardError("Cannot generate dashboard: department summary is empty.")

    if year is None:
        year = int(pd.to_datetime(df["Date"]).dt.year.max())

    try:
        html = build_dashboard_html(dept_summary, opportunities, monthly_trend, kpis, year, df)
        with open(output_file, "w", encoding="utf-8") as handle:
            handle.write(html)
    except DashboardError:
        raise
    except Exception as exc:
        raise DashboardError(f"Failed to write dashboard to {output_file!r}: {exc}") from exc

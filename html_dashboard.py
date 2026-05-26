"""Interactive, self-contained HTML dashboard (Plotly) for the F1 OPEX pipeline.

A pure presentation layer over the analysis outputs: a branded Red Bull "cockpit" with
KPI tiles and four interactive charts, emitted as a single offline-capable ``.html`` file
(plotly.js inlined once). Mirrors the Excel reporter's split — analysis *computes*, this
module *renders* — and reuses the same brand palette from ``constants.py``.
"""

from __future__ import annotations

from datetime import datetime
from string import Template
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from analysis import KpiSummary, Opportunity
from constants import (
    COLOR_DASH_BG,
    COLOR_DASH_FG,
    COLOR_DASH_GLOW,
    COLOR_DASH_GRID,
    COLOR_DASH_MUTED,
    COLOR_DASH_SURFACE,
    COLOR_NEGATIVE,
    COLOR_POSITIVE,
    COLOR_RB_BLUE,
    COLOR_RB_RED,
    COLOR_RB_YELLOW,
    DASH_FONT,
)
from exceptions import DashboardError

# Categorical palette for the spend-mix donut (Red Bull accents + harmonious tints)
_DEPT_PALETTE: tuple[str, ...] = (
    "#3671C6",
    "#E8002D",
    "#FFC906",
    "#2FD27A",
    "#9B6CFF",
    "#FF8A3D",
    "#36C6C6",
    "#FF5DA2",
)

_PLOTLY_CONFIG: dict[str, Any] = {"displayModeBar": False, "responsive": True}


def _compact_money(value: float) -> str:
    """Render a currency figure as a compact KPI string ($1.2M / $340K / $920)."""
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if magnitude >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"


def _style(fig: go.Figure, height: int) -> go.Figure:
    """Apply the shared dark-cockpit look to a figure — the HTML analogue of _style_chart."""
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=18, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=COLOR_DASH_FG, family=DASH_FONT, size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=COLOR_DASH_SURFACE, bordercolor=COLOR_DASH_GRID, font_size=12),
    )
    axis = dict(
        gridcolor="rgba(54,113,198,0.14)",  # faint blueprint grid, tied to the blue accent
        gridwidth=1,
        zerolinecolor="rgba(54,113,198,0.30)",
        linecolor=COLOR_DASH_GRID,
        color=COLOR_DASH_MUTED,
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
        marker_color=COLOR_RB_BLUE,
        hovertemplate="%{x}<br>Budget $%{y:,.0f}<extra></extra>",
    )
    fig.add_bar(
        name="Actual",
        x=dept_summary["Department"],
        y=dept_summary["Actual Amount"],
        marker_color=COLOR_RB_RED,
        hovertemplate="%{x}<br>Actual $%{y:,.0f}<extra></extra>",
    )
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.06)
    fig.update_xaxes(tickangle=-30)
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return _style(fig, 360)


def _spend_mix_fig(dept_summary: pd.DataFrame) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=dept_summary["Department"],
            values=dept_summary["Actual Amount"],
            hole=0.58,
            sort=True,
            direction="clockwise",
        )
    )
    fig.update_traces(
        marker=dict(colors=_DEPT_PALETTE, line=dict(color=COLOR_DASH_BG, width=2)),
        textinfo="percent",
        textfont_size=12,
        domain=dict(x=[0.0, 0.66]),
        hovertemplate="%{label}<br>$%{value:,.0f}<br>%{percent}<extra></extra>",
    )
    total = float(dept_summary["Actual Amount"].sum())
    fig = _style(fig, 360)
    fig.update_layout(
        legend=dict(orientation="v", x=0.72, y=0.5, font=dict(size=11)),
        annotations=[
            dict(
                text=f"<b>{_compact_money(total)}</b><br>"
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
        line=dict(color=COLOR_RB_BLUE, width=3),
        marker=dict(size=7),
        hovertemplate="%{x}<br>Budget $%{y:,.0f}<extra></extra>",
    )
    fig.add_scatter(
        name="Actual",
        x=months,
        y=monthly_trend["Actual Amount"],
        mode="lines+markers",
        line=dict(color=COLOR_RB_RED, width=3),
        marker=dict(size=7),
        fill="tozeroy",
        fillcolor="rgba(232,0,45,0.10)",
        hovertemplate="%{x}<br>Actual $%{y:,.0f}<extra></extra>",
    )
    fig.update_yaxes(tickprefix="$", tickformat="~s")
    return _style(fig, 340)


def _variance_ranking_fig(dept_summary: pd.DataFrame) -> go.Figure:
    # Ascending → most negative at the bottom, biggest overspend at the top.
    ranked = dept_summary.sort_values("Variance")
    colors = [COLOR_NEGATIVE if v > 0 else COLOR_POSITIVE for v in ranked["Variance"]]
    fig = go.Figure()
    fig.add_bar(
        orientation="h",
        y=ranked["Department"],
        x=ranked["Variance"],
        marker_color=colors,
        text=[_compact_money(v) for v in ranked["Variance"]],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}<br>Variance $%{x:,.0f}<extra></extra>",
    )
    fig.update_layout(showlegend=False)
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


def _kpi_card(caption: str, value: str, accent: str, value_class: str = "") -> str:
    return (
        f'<div class="kpi hud" style="border-top-color:{accent}">'
        f'<div class="cap">{caption}</div>'
        f'<div class="val {value_class}">{value}</div></div>'
    )


_CSS = Template("""
* { box-sizing: border-box; }
body { margin: 0; color: $FG; font-family: $FONT; -webkit-font-smoothing: antialiased;
       background-color: $BG;
       background-image:
         radial-gradient(1200px 480px at 50% -10%, rgba(54,113,198,.18), transparent 70%),
         linear-gradient(rgba(54,113,198,.045) 1px, transparent 1px),
         linear-gradient(90deg, rgba(54,113,198,.045) 1px, transparent 1px);
       background-size: auto, 44px 44px, 44px 44px;
       background-attachment: fixed; }
.wrap { max-width: 1480px; margin: 0 auto; padding: 28px 24px 52px; }
/* HUD corner brackets — thin Red Bull-blue L's at opposite corners */
.hud { position: relative; }
.hud::before, .hud::after { content: ""; position: absolute; width: 16px; height: 16px;
       border: 1.5px solid $BLUE; pointer-events: none;
       filter: drop-shadow(0 0 4px rgba(54,113,198,.75)); }
.hud::before { top: 9px; left: 9px; border-right: 0; border-bottom: 0; border-top-left-radius: 4px; }
.hud::after { bottom: 9px; right: 9px; border-left: 0; border-top: 0; border-bottom-right-radius: 4px; }
.banner { display: flex; align-items: center; justify-content: space-between; gap: 18px;
          background: linear-gradient(135deg, #101A40, #1B2A63); border: 1px solid $GRID;
          border-radius: 18px; padding: 22px 28px;
          box-shadow: 0 12px 34px rgba(0,0,0,.40), inset 0 0 0 1px rgba(54,113,198,.16),
                      0 0 38px rgba(54,113,198,.12); }
.banner .title { font-size: 27px; font-weight: 800; letter-spacing: .04em;
                 text-shadow: 0 0 22px rgba(54,113,198,.30); }
.banner .sub { color: $MUTED; font-size: 13px; margin-top: 6px; letter-spacing: .02em; }
.stripe { display: flex; gap: 6px; margin-top: 14px; }
.stripe span { height: 6px; width: 46px; border-radius: 3px; box-shadow: 0 0 10px currentColor; }
.right { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; }
.live { display: inline-flex; align-items: center; gap: 8px; font-size: 11px; font-weight: 700;
        letter-spacing: .24em; text-transform: uppercase; color: $BLUE; }
.live .dot { width: 8px; height: 8px; border-radius: 50%; background: $BLUE;
             box-shadow: 0 0 8px $BLUE, 0 0 16px $BLUE; }
.badge { font-size: 26px; font-weight: 800; color: $YELLOW; letter-spacing: .04em;
         border: 1px solid $GRID; border-radius: 12px; padding: 10px 16px;
         background: rgba(255,201,6,.06); box-shadow: 0 0 20px rgba(255,201,6,.10); }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 22px 0; }
.kpi { background: linear-gradient(180deg, rgba(28,40,86,.92), rgba(18,28,64,.92));
       border: 1px solid $GRID; border-top: 3px solid $BLUE; border-radius: 14px;
       padding: 18px 20px 20px 22px;
       box-shadow: 0 6px 18px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.04),
                   0 0 0 1px rgba(54,113,198,.06);
       transition: transform .18s ease, box-shadow .18s ease; }
.kpi:hover { transform: translateY(-3px);
             box-shadow: 0 12px 26px rgba(0,0,0,.34), 0 0 24px rgba(54,113,198,.22); }
.kpi .cap { font-size: 10.5px; letter-spacing: .16em; text-transform: uppercase; color: $MUTED; }
.kpi .val { font-size: 32px; font-weight: 800; margin-top: 10px; line-height: 1.1;
            text-shadow: 0 0 18px $GLOW; }
.pos { color: $POS; text-shadow: 0 0 18px rgba(47,210,122,.42); }
.neg { color: $NEG; text-shadow: 0 0 18px rgba(255,77,94,.42); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { background: linear-gradient(180deg, rgba(24,34,76,.86), rgba(16,24,58,.86));
        border: 1px solid $GRID; border-radius: 16px; padding: 16px 16px 8px;
        box-shadow: 0 6px 18px rgba(0,0,0,.28), 0 0 0 1px rgba(54,113,198,.06);
        margin-bottom: 16px; transition: box-shadow .18s ease; }
.card:hover { box-shadow: 0 10px 24px rgba(0,0,0,.32), 0 0 24px rgba(54,113,198,.16); }
.card h3 { margin: 6px 6px 8px 20px; font-size: 14px; font-weight: 700; letter-spacing: .05em;
           text-transform: uppercase; color: $FG; }
.section { font-size: 13px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase;
           margin: 26px 4px 14px; color: $FG; display: flex; align-items: center; gap: 10px; }
.section::before { content: ""; width: 22px; height: 2px; background: $BLUE; border-radius: 2px;
                   box-shadow: 0 0 10px $BLUE; }
.savings { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.save { background: linear-gradient(180deg, rgba(24,34,76,.86), rgba(16,24,58,.86));
        border: 1px solid $GRID; border-left: 4px solid $YELLOW; border-radius: 14px;
        padding: 16px 18px;
        box-shadow: 0 6px 18px rgba(0,0,0,.28), 0 0 0 1px rgba(54,113,198,.06); }
.save .t { font-weight: 700; font-size: 15px; }
.save .n { color: $MUTED; font-size: 12px; margin-top: 4px; }
.save .amt { font-size: 24px; font-weight: 800; color: $YELLOW; margin-top: 10px;
             text-shadow: 0 0 16px rgba(255,201,6,.35); }
@media (max-width: 980px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .grid2 { grid-template-columns: 1fr; }
  .savings { grid-template-columns: 1fr; }
}
""")


def build_dashboard_html(
    dept_summary: pd.DataFrame,
    opportunities: list[Opportunity],
    monthly_trend: pd.DataFrame,
    kpis: KpiSummary,
    year: int,
) -> str:
    """Assemble the full self-contained dashboard HTML document as a string."""
    css = _CSS.substitute(
        BG=COLOR_DASH_BG,
        FG=COLOR_DASH_FG,
        FONT=DASH_FONT,
        GRID=COLOR_DASH_GRID,
        MUTED=COLOR_DASH_MUTED,
        SURFACE=COLOR_DASH_SURFACE,
        BLUE=COLOR_RB_BLUE,
        YELLOW=COLOR_RB_YELLOW,
        POS=COLOR_POSITIVE,
        NEG=COLOR_NEGATIVE,
        GLOW=COLOR_DASH_GLOW,
    )

    generated = datetime.now().strftime("%d %b %Y")
    banner = (
        '<div class="banner hud"><div>'
        '<div class="title">RED BULL RACING &mdash; F1 OPEX</div>'
        f'<div class="sub">Operational expenditure cockpit &middot; FY{year} &middot; '
        f'{kpis["num_transactions"]:,} transactions &middot; generated {generated}</div>'
        f'<div class="stripe">'
        f'<span style="background:{COLOR_RB_BLUE};color:{COLOR_RB_BLUE}"></span>'
        f'<span style="background:{COLOR_RB_RED};color:{COLOR_RB_RED}"></span>'
        f'<span style="background:{COLOR_RB_YELLOW};color:{COLOR_RB_YELLOW}"></span></div>'
        '</div><div class="right">'
        '<div class="live"><span class="dot"></span>Live</div>'
        f'<div class="badge">FY{year}</div></div></div>'
    )

    over = kpis["total_variance"] > 0
    arrow = "&#9650;" if over else "&#9660;"  # ▲ / ▼
    vcls = "neg" if over else "pos"
    depts_over = kpis["departments_over_budget"]
    kpi_cards = "".join(
        [
            _kpi_card("Total Budget", _compact_money(kpis["total_budget"]), COLOR_RB_BLUE),
            _kpi_card("Total Actual", _compact_money(kpis["total_actual"]), COLOR_RB_RED),
            _kpi_card(
                "Total Variance",
                f'{arrow} {_compact_money(abs(kpis["total_variance"]))}',
                COLOR_RB_RED,
                vcls,
            ),
            _kpi_card("Variance %", f'{arrow} {abs(kpis["variance_pct"]):.1%}', COLOR_RB_RED, vcls),
            _kpi_card(
                "Potential Savings", _compact_money(kpis["potential_savings"]), COLOR_RB_YELLOW
            ),
            _kpi_card("Opportunities", f'{kpis["num_opportunities"]}', COLOR_RB_BLUE),
            _kpi_card(
                "Depts Over Budget",
                f"{depts_over} / {len(dept_summary)}",
                COLOR_RB_RED,
                "neg" if depts_over else "pos",
            ),
            _kpi_card("Transactions", f'{kpis["num_transactions"]:,}', COLOR_DASH_MUTED),
        ]
    )
    kpi_band = f'<div class="kpis">{kpi_cards}</div>'

    charts = [
        ("Budget vs. Actual by Department", _budget_actual_fig(dept_summary)),
        ("Actual Spend Mix by Department", _spend_mix_fig(dept_summary)),
        ("Monthly Budget vs. Actual Spend", _monthly_trend_fig(monthly_trend)),
        ("Department Variance vs. Budget", _variance_ranking_fig(dept_summary)),
    ]
    divs = [
        pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs="inline" if i == 0 else False,
            config=_PLOTLY_CONFIG,
        )
        for i, (_, fig) in enumerate(charts)
    ]

    def card(title: str, body: str) -> str:
        return f'<div class="card hud"><h3>{title}</h3>{body}</div>'

    charts_html = (
        f'<div class="grid2">{card(charts[0][0], divs[0])}{card(charts[1][0], divs[1])}</div>'
        f"{card(charts[2][0], divs[2])}"
        f"{card(charts[3][0], divs[3])}"
    )

    if opportunities:
        saves = "".join(
            f'<div class="save hud"><div class="t">{opp["Type"]}</div>'
            f'<div class="n">{opp["Count"]} item(s) flagged</div>'
            f'<div class="amt">{_compact_money(opp["Potential Savings"])}</div></div>'
            for opp in opportunities
        )
        savings_html = (
            '<div class="section">Identified Savings Opportunities</div>'
            f'<div class="savings">{saves}</div>'
        )
    else:
        savings_html = (
            '<div class="section">Identified Savings Opportunities</div>'
            '<div class="save"><div class="t">No opportunities flagged</div>'
            '<div class="n">All spending is within the configured detection thresholds.</div></div>'
        )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Red Bull Racing &mdash; F1 OPEX Dashboard</title>"
        f'<style>{css}</style></head><body><div class="wrap">'
        f"{banner}{kpi_band}{charts_html}{savings_html}"
        "</div></body></html>"
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
        html = build_dashboard_html(dept_summary, opportunities, monthly_trend, kpis, year)
        with open(output_file, "w", encoding="utf-8") as handle:
            handle.write(html)
    except DashboardError:
        raise
    except Exception as exc:
        raise DashboardError(f"Failed to write dashboard to {output_file!r}: {exc}") from exc

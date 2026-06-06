import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from analysis import KpiSummary, Opportunity
from constants import (
    COLOR_CARD_BG,
    COLOR_CARD_FG,
    COLOR_HEADER_BG,
    COLOR_MUTED_FG,
    COLOR_OVERSPEND_BG,
    COLOR_OVERSPEND_FG,
    COLOR_RB_BLUE,
    COLOR_RB_NAVY,
    COLOR_RB_RED,
    COLOR_RB_YELLOW,
    COLOR_SAVING_BG,
    COLOR_SAVING_FG,
    COLOR_WHITE,
    TOP_EXPENSE_TYPES,
    VARIANCE_FLAG_THRESHOLD,
)
from exceptions import ReportError

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportContext:
    writer: pd.ExcelWriter
    workbook: Any
    fmts: dict[str, Any]


def _make_formats(workbook: Any) -> dict[str, Any]:
    card_base = {"bg_color": COLOR_CARD_BG, "border": 1, "border_color": COLOR_WHITE}
    return {
        "header": workbook.add_format({"bold": True, "bg_color": COLOR_HEADER_BG, "border": 1}),
        "title": workbook.add_format({"bold": True, "font_size": 14}),
        "bold": workbook.add_format({"bold": True}),
        "currency": workbook.add_format({"num_format": "$#,##0.00"}),
        "percent": workbook.add_format({"num_format": "0.00%"}),
        "red": workbook.add_format(
            {"bg_color": COLOR_OVERSPEND_BG, "font_color": COLOR_OVERSPEND_FG}
        ),
        "green": workbook.add_format({"bg_color": COLOR_SAVING_BG, "font_color": COLOR_SAVING_FG}),
        # Dashboard cockpit
        "banner_title": workbook.add_format(
            {
                "bold": True,
                "font_size": 22,
                "font_color": COLOR_WHITE,
                "bg_color": COLOR_RB_NAVY,
                "align": "left",
                "valign": "vcenter",
            }
        ),
        "banner_sub": workbook.add_format(
            {
                "font_size": 10,
                "font_color": COLOR_RB_YELLOW,
                "bg_color": COLOR_RB_NAVY,
                "align": "left",
                "valign": "vcenter",
            }
        ),
        "card_caption": workbook.add_format(
            {
                **card_base,
                "font_size": 9,
                "bold": True,
                "font_color": COLOR_MUTED_FG,
                "align": "left",
                "valign": "top",
            }
        ),
        "card_value": workbook.add_format(
            {
                **card_base,
                "font_size": 20,
                "bold": True,
                "font_color": COLOR_CARD_FG,
                "align": "left",
                "valign": "top",
            }
        ),
        "card_value_red": workbook.add_format(
            {
                **card_base,
                "font_size": 20,
                "bold": True,
                "font_color": COLOR_OVERSPEND_FG,
                "align": "left",
                "valign": "top",
            }
        ),
        "card_value_green": workbook.add_format(
            {
                **card_base,
                "font_size": 20,
                "bold": True,
                "font_color": COLOR_SAVING_FG,
                "align": "left",
                "valign": "top",
            }
        ),
    }


def _style_chart(chart: Any, *, legend: str | None = "bottom") -> None:
    """Apply a consistent, de-cluttered look to every chart in the workbook."""
    chart.set_style(2)
    chart.set_chartarea({"border": {"none": True}})
    chart.set_plotarea({"border": {"none": True}})
    if legend is None:
        chart.set_legend({"none": True})
    else:
        chart.set_legend({"position": legend, "font": {"size": 9}})


def _compact_money(value: float) -> str:
    """Render a currency figure as a compact KPI string ($1.2M / $340K / $920)."""
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if magnitude >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"


def _write_dashboard(
    ctx: ReportContext,
    kpis: KpiSummary,
    dept_summary: pd.DataFrame,
    monthly_trend: pd.DataFrame,
    year: int,
) -> None:
    """Executive cockpit: branded banner, KPI cards, and headline charts.

    Charts reference ranges on the Executive Summary / Monthly Trends sheets, so the
    dashboard never duplicates data — it is a pure presentation layer.
    """
    ws = ctx.workbook.add_worksheet("Dashboard")
    ws.set_tab_color(COLOR_RB_NAVY)
    ws.hide_gridlines(2)
    ws.set_column("A:H", 15)

    # Branded banner
    ws.set_row(0, 32)
    ws.set_row(1, 16)
    ws.merge_range(
        0, 0, 0, 7, f"RED BULL RACING  —  F1 OPEX  ·  FY{year}", ctx.fmts["banner_title"]
    )
    generated = datetime.now().strftime("%d %b %Y")
    ws.merge_range(
        1,
        0,
        1,
        7,
        f"Operational expenditure overview · {kpis['num_transactions']:,} transactions"
        f" · generated {generated}",
        ctx.fmts["banner_sub"],
    )

    # KPI cards (4 across, 2 rows)
    def card(top_row: int, left_col: int, caption: str, value: str, value_fmt: str) -> None:
        ws.merge_range(top_row, left_col, top_row, left_col + 1, caption, ctx.fmts["card_caption"])
        ws.merge_range(top_row + 1, left_col, top_row + 2, left_col + 1, value, ctx.fmts[value_fmt])

    for r in (4, 5, 7, 8):
        ws.set_row(r, 18)

    over = kpis["total_variance"] > 0
    arrow = "▲" if over else "▼"
    var_fmt = "card_value_red" if over else "card_value_green"
    depts_over = kpis["departments_over_budget"]
    n_depts = len(dept_summary)

    card(3, 0, "TOTAL BUDGET", _compact_money(kpis["total_budget"]), "card_value")
    card(3, 2, "TOTAL ACTUAL", _compact_money(kpis["total_actual"]), "card_value")
    card(3, 4, "TOTAL VARIANCE", f"{arrow} {_compact_money(abs(kpis['total_variance']))}", var_fmt)
    card(3, 6, "VARIANCE %", f"{arrow} {abs(kpis['variance_pct']):.1%}", var_fmt)

    card(6, 0, "POTENTIAL SAVINGS", _compact_money(kpis["potential_savings"]), "card_value")
    card(6, 2, "OPPORTUNITIES FLAGGED", f"{kpis['num_opportunities']}", "card_value")
    card(
        6,
        4,
        "DEPTS OVER BUDGET",
        f"{depts_over} / {n_depts}",
        "card_value_red" if depts_over else "card_value_green",
    )
    card(6, 6, "TRANSACTIONS", f"{kpis['num_transactions']:,}", "card_value")

    # Headline charts reference ranges on other sheets — no data is duplicated here.
    n = len(dept_summary)
    first, last = 2, 1 + n  # Executive Summary data rows

    budget_actual = ctx.workbook.add_chart({"type": "column"})
    budget_actual.add_series(
        {
            "name": "Budget",
            "categories": ["Executive Summary", first, 0, last, 0],
            "values": ["Executive Summary", first, 1, last, 1],
            "fill": {"color": COLOR_RB_BLUE},
        }
    )
    budget_actual.add_series(
        {
            "name": "Actual",
            "categories": ["Executive Summary", first, 0, last, 0],
            "values": ["Executive Summary", first, 2, last, 2],
            "fill": {"color": COLOR_RB_RED},
        }
    )
    budget_actual.set_title({"name": "Budget vs. Actual by Department"})
    budget_actual.set_y_axis({"num_format": "$#,##0"})
    budget_actual.set_size({"width": 440, "height": 300})
    _style_chart(budget_actual)
    ws.insert_chart("A11", budget_actual)

    spend_mix = ctx.workbook.add_chart({"type": "doughnut"})
    spend_mix.add_series(
        {
            "name": "Spend Mix",
            "categories": ["Executive Summary", first, 0, last, 0],
            "values": ["Executive Summary", first, 2, last, 2],
        }
    )
    spend_mix.set_title({"name": "Actual Spend Mix by Department"})
    spend_mix.set_hole_size(55)
    spend_mix.set_size({"width": 440, "height": 300})
    _style_chart(spend_mix, legend="right")
    ws.insert_chart("E11", spend_mix)

    months = len(monthly_trend)
    m_first, m_last = 2, 1 + months  # Monthly Trends data rows
    trend = ctx.workbook.add_chart({"type": "line"})
    trend.add_series(
        {
            "name": "Budget",
            "categories": ["Monthly Trends", m_first, 0, m_last, 0],
            "values": ["Monthly Trends", m_first, 1, m_last, 1],
            "line": {"color": COLOR_RB_BLUE, "width": 2.25},
            "marker": {"type": "circle", "size": 5},
        }
    )
    trend.add_series(
        {
            "name": "Actual",
            "categories": ["Monthly Trends", m_first, 0, m_last, 0],
            "values": ["Monthly Trends", m_first, 2, m_last, 2],
            "line": {"color": COLOR_RB_RED, "width": 2.25},
            "marker": {"type": "circle", "size": 5},
        }
    )
    trend.set_title({"name": "Monthly Budget vs. Actual Spend"})
    trend.set_y_axis({"num_format": "$#,##0"})
    trend.set_size({"width": 920, "height": 300})
    _style_chart(trend)
    ws.insert_chart("A27", trend)


def _write_executive_summary(ctx: ReportContext, dept_summary: pd.DataFrame) -> None:
    n = len(dept_summary)
    dept_summary.to_excel(ctx.writer, sheet_name="Executive Summary", index=False, startrow=1)
    ws = ctx.writer.sheets["Executive Summary"]
    ws.write(0, 0, "Departmental OPEX Overview", ctx.fmts["title"])
    ws.set_row(1, None, ctx.fmts["header"])
    ws.freeze_panes(2, 0)
    ws.set_column("A:A", 22, None)
    ws.set_column("B:D", 16, ctx.fmts["currency"])
    ws.set_column("E:E", 13, ctx.fmts["percent"])

    # dept_summary columns (0-indexed): Department=0, Budgeted Amount=1,
    #   Actual Amount=2, Variance=3, Variance %=4
    # Excel rows: header at row 1, data at rows 2..(1+n)
    first_data, last_data = 2, 1 + n

    data_range = f"E3:E{2 + n}"
    ws.conditional_format(
        data_range,
        {
            "type": "cell",
            "criteria": ">",
            "value": VARIANCE_FLAG_THRESHOLD,
            "format": ctx.fmts["red"],
        },
    )
    ws.conditional_format(
        data_range,
        {
            "type": "cell",
            "criteria": "<",
            "value": 0,
            "format": ctx.fmts["green"],
        },
    )

    # Data bars on the Variance ($) column for at-a-glance magnitude.
    ws.conditional_format(
        f"D3:D{2 + n}",
        {"type": "data_bar", "bar_color": COLOR_RB_BLUE},
    )

    c1 = ctx.workbook.add_chart({"type": "column"})
    c1.add_series(
        {
            "name": "Budget",
            "categories": ["Executive Summary", first_data, 0, last_data, 0],
            "values": ["Executive Summary", first_data, 1, last_data, 1],
            "fill": {"color": COLOR_RB_BLUE},
        }
    )
    c1.add_series(
        {
            "name": "Actual",
            "categories": ["Executive Summary", first_data, 0, last_data, 0],
            "values": ["Executive Summary", first_data, 2, last_data, 2],
            "fill": {"color": COLOR_RB_RED},
        }
    )
    c1.set_title({"name": "Budget vs. Actual by Department"})
    c1.set_x_axis({"name": "Department"})
    c1.set_y_axis({"name": "Amount ($)", "num_format": "$#,##0"})
    _style_chart(c1)
    ws.insert_chart("G2", c1)

    c2 = ctx.workbook.add_chart({"type": "column"})
    c2.add_series(
        {
            "name": "Variance %",
            "categories": ["Executive Summary", first_data, 0, last_data, 0],
            "values": ["Executive Summary", first_data, 4, last_data, 4],
            "fill": {"color": COLOR_RB_RED},
        }
    )
    c2.set_title({"name": "Variance % by Department"})
    c2.set_x_axis({"name": "Department"})
    c2.set_y_axis({"name": "Variance %", "num_format": "0%"})
    _style_chart(c2, legend=None)
    ws.insert_chart("G20", c2)


def _write_savings_opportunities(
    ctx: ReportContext,
    opportunities: list[Opportunity],
) -> None:
    ws = ctx.workbook.add_worksheet("Savings Opportunities")
    ws.write(0, 0, "Identified Cost Savings Opportunities", ctx.fmts["title"])
    ws.set_column("A:B", 22, None)
    ws.set_column("C:C", 42, None)
    ws.set_column("D:D", 16, ctx.fmts["currency"])

    row = 2
    for opp in opportunities:
        ws.write(row, 0, f"Type: {opp['Type']}", ctx.fmts["bold"])
        ws.write(row, 1, f"Potential Savings: ${opp['Potential Savings']:,.2f}", ctx.fmts["red"])
        row += 1
        details = opp["Details"]
        if details:
            cols = list(details[0].keys())
            for col_num, col_name in enumerate(cols):
                ws.write(row, col_num, col_name, ctx.fmts["header"])
            for i, record in enumerate(details):
                for col_num, col_name in enumerate(cols):
                    ws.write(row + 1 + i, col_num, record[col_name])
            row += len(details) + 2


def _write_monthly_trends(
    ctx: ReportContext,
    df: pd.DataFrame,
    monthly_trend: pd.DataFrame,
) -> None:
    n_months = len(monthly_trend)
    monthly_trend.to_excel(ctx.writer, sheet_name="Monthly Trends", index=False, startrow=1)
    ws = ctx.writer.sheets["Monthly Trends"]
    ws.write(0, 0, "Monthly Spend & Expense Type Analysis", ctx.fmts["title"])
    ws.set_row(1, None, ctx.fmts["header"])
    ws.freeze_panes(2, 0)
    ws.set_column("A:A", 14, None)
    ws.set_column("B:C", 16, ctx.fmts["currency"])

    # monthly_trend columns: Month Name=0, Budgeted Amount=1, Actual Amount=2
    # data rows: 2..(1+n_months)
    first_data, last_data = 2, 1 + n_months

    c3 = ctx.workbook.add_chart({"type": "line"})
    c3.add_series(
        {
            "name": "Budget",
            "categories": ["Monthly Trends", first_data, 0, last_data, 0],
            "values": ["Monthly Trends", first_data, 1, last_data, 1],
            "line": {"color": COLOR_RB_BLUE, "width": 2},
            "marker": {"type": "circle", "size": 5},
        }
    )
    c3.add_series(
        {
            "name": "Actual",
            "categories": ["Monthly Trends", first_data, 0, last_data, 0],
            "values": ["Monthly Trends", first_data, 2, last_data, 2],
            "line": {"color": COLOR_RB_RED, "width": 2},
            "marker": {"type": "circle", "size": 5},
        }
    )
    c3.set_title({"name": "Monthly Budget vs. Actual Spend"})
    c3.set_x_axis({"name": "Month"})
    c3.set_y_axis({"name": "Amount ($)", "num_format": "$#,##0"})
    c3.set_size({"width": 540, "height": 288})
    ws.insert_chart("E2", c3)

    # Top expense types by actual spend, written inline rather than from a sheet range.
    expense_summary = (
        df.groupby("Expense Type", as_index=False)
        .agg({"Actual Amount": "sum"})
        .sort_values("Actual Amount", ascending=False)
        .head(TOP_EXPENSE_TYPES)
        .reset_index(drop=True)
    )
    n_exp = len(expense_summary)
    exp_hdr = n_months + 3
    exp_data_start = exp_hdr + 1
    exp_data_end = exp_data_start + n_exp - 1

    ws.write(exp_hdr, 0, "Expense Type", ctx.fmts["header"])
    ws.write(exp_hdr, 1, "Actual Amount", ctx.fmts["header"])
    expense_types: list[str] = expense_summary["Expense Type"].tolist()
    actual_amounts: list[float] = expense_summary["Actual Amount"].tolist()
    for idx, (expense_type, actual_amount) in enumerate(zip(expense_types, actual_amounts)):
        ws.write(exp_data_start + idx, 0, expense_type)
        ws.write(exp_data_start + idx, 1, actual_amount, ctx.fmts["currency"])

    c4 = ctx.workbook.add_chart({"type": "bar"})
    c4.add_series(
        {
            "name": "Actual Spend",
            "categories": ["Monthly Trends", exp_data_start, 0, exp_data_end, 0],
            "values": ["Monthly Trends", exp_data_start, 1, exp_data_end, 1],
            "fill": {"color": COLOR_RB_BLUE},
        }
    )
    c4.set_title({"name": "Top Expense Types by Actual Spend"})
    c4.set_x_axis({"name": "Amount ($)", "num_format": "$#,##0"})
    c4.set_y_axis({"name": "Expense Type"})
    c4.set_size({"width": 540, "height": 360})
    ws.insert_chart("E22", c4)


def _write_detailed_data(ctx: ReportContext, df: pd.DataFrame) -> None:
    df.to_excel(ctx.writer, sheet_name="Detailed Data", index=False)
    ws = ctx.writer.sheets["Detailed Data"]
    ws.set_row(0, None, ctx.fmts["header"])
    ws.freeze_panes(1, 0)
    ws.set_column("A:A", 14, None)
    ws.set_column("B:D", 22, None)
    ws.set_column("E:E", 42, None)
    ws.set_column("F:H", 16, ctx.fmts["currency"])
    ws.set_column("I:I", 13, ctx.fmts["percent"])

    # Variance % column (I) — same red/green rules as Executive Summary
    data_range = f"I2:I{1 + len(df)}"
    ws.conditional_format(
        data_range,
        {
            "type": "cell",
            "criteria": ">",
            "value": VARIANCE_FLAG_THRESHOLD,
            "format": ctx.fmts["red"],
        },
    )
    ws.conditional_format(
        data_range,
        {
            "type": "cell",
            "criteria": "<",
            "value": 0,
            "format": ctx.fmts["green"],
        },
    )


def create_excel_report(
    df: pd.DataFrame,
    dept_summary: pd.DataFrame,
    opportunities: list[Opportunity],
    monthly_trend: pd.DataFrame,
    kpis: KpiSummary,
    output_file: str = "opex_analysis_report.xlsx",
    year: int | None = None,
) -> None:
    """Write a 5-sheet Excel workbook (cockpit Dashboard + 4 detail sheets) with 7 charts."""
    if dept_summary.empty:
        raise ReportError("Cannot generate report: department summary is empty.")

    if year is None:
        year = int(pd.to_datetime(df["Date"]).dt.year.max())

    try:
        with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
            ctx = ReportContext(
                writer=writer,
                workbook=writer.book,
                fmts=_make_formats(writer.book),
            )
            _write_dashboard(ctx, kpis, dept_summary, monthly_trend, year)
            _write_executive_summary(ctx, dept_summary)
            _write_savings_opportunities(ctx, opportunities)
            _write_monthly_trends(ctx, df, monthly_trend)
            _write_detailed_data(ctx, df)
    except ReportError:
        raise
    except Exception as exc:
        raise ReportError(f"Failed to write report to {output_file!r}: {exc}") from exc

import logging
from typing import Any

import pandas as pd

from analysis import Opportunity
from constants import (
    COLOR_HEADER_BG,
    COLOR_OVERSPEND_BG,
    COLOR_OVERSPEND_FG,
    COLOR_RB_BLUE,
    COLOR_RB_RED,
    COLOR_SAVING_BG,
    COLOR_SAVING_FG,
    TOP_EXPENSE_TYPES,
    VARIANCE_FLAG_THRESHOLD,
)
from exceptions import ReportError

_logger = logging.getLogger(__name__)


def _make_formats(workbook: Any) -> dict[str, Any]:
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
    }


def _write_executive_summary(
    writer: pd.ExcelWriter,
    workbook: Any,
    dept_summary: pd.DataFrame,
    fmts: dict[str, Any],
) -> None:
    n = len(dept_summary)
    dept_summary.to_excel(writer, sheet_name="Executive Summary", index=False, startrow=1)
    ws = writer.sheets["Executive Summary"]
    ws.write(0, 0, "Departmental OPEX Overview", fmts["title"])
    ws.set_row(1, None, fmts["header"])
    ws.freeze_panes(2, 0)
    ws.set_column("A:A", 22, None)
    ws.set_column("B:D", 16, fmts["currency"])
    ws.set_column("E:E", 13, fmts["percent"])

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
            "format": fmts["red"],
        },
    )
    ws.conditional_format(
        data_range,
        {
            "type": "cell",
            "criteria": "<",
            "value": 0,
            "format": fmts["green"],
        },
    )

    # Chart 1: Budget vs Actual side-by-side
    c1 = workbook.add_chart({"type": "column"})
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
    ws.insert_chart("G2", c1)

    # Chart 2: Variance % per department
    c2 = workbook.add_chart({"type": "column"})
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
    ws.insert_chart("G20", c2)


def _write_savings_opportunities(
    workbook: Any,
    opportunities: list[Opportunity],
    fmts: dict[str, Any],
) -> None:
    ws = workbook.add_worksheet("Savings Opportunities")
    ws.write(0, 0, "Identified Cost Savings Opportunities", fmts["title"])
    ws.set_column("A:B", 22, None)
    ws.set_column("C:C", 42, None)
    ws.set_column("D:D", 16, fmts["currency"])

    row = 2
    for opp in opportunities:
        ws.write(row, 0, f"Type: {opp['Type']}", fmts["bold"])
        ws.write(row, 1, f"Potential Savings: ${opp['Potential Savings']:,.2f}", fmts["red"])
        row += 1
        details = opp["Details"]
        if details:
            cols = list(details[0].keys())
            for col_num, col_name in enumerate(cols):
                ws.write(row, col_num, col_name, fmts["header"])
            for i, record in enumerate(details):
                for col_num, col_name in enumerate(cols):
                    ws.write(row + 1 + i, col_num, record[col_name])
            row += len(details) + 2


def _write_monthly_trends(
    writer: pd.ExcelWriter,
    workbook: Any,
    df: pd.DataFrame,
    monthly_trend: pd.DataFrame,
    fmts: dict[str, Any],
) -> None:
    n_months = len(monthly_trend)
    monthly_trend.to_excel(writer, sheet_name="Monthly Trends", index=False, startrow=1)
    ws = writer.sheets["Monthly Trends"]
    ws.write(0, 0, "Monthly Spend & Expense Type Analysis", fmts["title"])
    ws.set_row(1, None, fmts["header"])
    ws.freeze_panes(2, 0)
    ws.set_column("A:A", 14, None)
    ws.set_column("B:C", 16, fmts["currency"])

    # monthly_trend columns: Month Name=0, Budgeted Amount=1, Actual Amount=2
    # data rows: 2..(1+n_months)
    first_data, last_data = 2, 1 + n_months

    # Chart 3: Monthly Budget vs Actual line chart
    c3 = workbook.add_chart({"type": "line"})
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

    # Expense type breakdown — top 10 by actual spend, written manually
    expense_summary = (
        df.groupby("Expense Type", as_index=False)
        .agg({"Actual Amount": "sum"})
        .sort_values("Actual Amount", ascending=False)
        .head(TOP_EXPENSE_TYPES)
        .reset_index(drop=True)
    )
    n_exp = len(expense_summary)
    exp_hdr = n_months + 3  # header row for expense table
    exp_data_start = exp_hdr + 1
    exp_data_end = exp_data_start + n_exp - 1

    ws.write(exp_hdr, 0, "Expense Type", fmts["header"])
    ws.write(exp_hdr, 1, "Actual Amount", fmts["header"])
    expense_types: list[str] = expense_summary["Expense Type"].tolist()
    actual_amounts: list[float] = expense_summary["Actual Amount"].tolist()
    for idx, (expense_type, actual_amount) in enumerate(zip(expense_types, actual_amounts)):
        ws.write(exp_data_start + idx, 0, expense_type)
        ws.write(exp_data_start + idx, 1, actual_amount, fmts["currency"])

    # Chart 4: Expense type horizontal bar chart
    c4 = workbook.add_chart({"type": "bar"})
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


def _write_detailed_data(
    writer: pd.ExcelWriter,
    df: pd.DataFrame,
    fmts: dict[str, Any],
) -> None:
    df.to_excel(writer, sheet_name="Detailed Data", index=False)
    ws = writer.sheets["Detailed Data"]
    ws.set_row(0, None, fmts["header"])
    ws.freeze_panes(1, 0)
    ws.set_column("A:A", 14, None)
    ws.set_column("B:D", 22, None)
    ws.set_column("E:E", 42, None)
    ws.set_column("F:H", 16, fmts["currency"])
    ws.set_column("I:I", 13, fmts["percent"])


def create_excel_report(
    df: pd.DataFrame,
    dept_summary: pd.DataFrame,
    opportunities: list[Opportunity],
    monthly_trend: pd.DataFrame,
    output_file: str = "opex_analysis_report.xlsx",
) -> None:
    """Write a 4-sheet Excel workbook with 4 charts summarizing OPEX spend."""
    if dept_summary.empty:
        raise ReportError("Cannot generate report: department summary is empty.")

    try:
        with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
            workbook = writer.book
            fmts = _make_formats(workbook)
            _write_executive_summary(writer, workbook, dept_summary, fmts)
            _write_savings_opportunities(workbook, opportunities, fmts)
            _write_monthly_trends(writer, workbook, df, monthly_trend, fmts)
            _write_detailed_data(writer, df, fmts)
    except ReportError:
        raise
    except Exception as exc:
        raise ReportError(f"Failed to write report to {output_file!r}: {exc}") from exc

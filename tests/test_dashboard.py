import os
import tempfile

import pandas as pd

import analysis
import data_generator
import html_dashboard
from formatting import compact_money


def _pipeline_outputs(
    *, records: int = 80, seed: int = 3, inject: bool = True
) -> tuple[
    pd.DataFrame, pd.DataFrame, list[analysis.Opportunity], pd.DataFrame, analysis.KpiSummary
]:
    df = data_generator.generate_opex_data(num_records=records, seed=seed, inject_anomalies=inject)
    df = analysis.calculate_variance(df)
    dept_summary = analysis.analyze_department_spending(df)
    opportunities = analysis.identify_savings_opportunities(df)
    monthly_trend = analysis.compute_monthly_trend(df)
    kpis = analysis.compute_kpis(df, opportunities)
    return df, dept_summary, opportunities, monthly_trend, kpis


def test_build_dashboard_html_contains_branding_and_kpis() -> None:
    _, dept_summary, opportunities, monthly_trend, kpis = _pipeline_outputs()
    html = html_dashboard.build_dashboard_html(
        dept_summary, opportunities, monthly_trend, kpis, year=2025
    )

    assert html.startswith("<!DOCTYPE html>")
    assert "RED BULL RACING" in html
    assert "FY2025" in html
    for caption in (
        "Total Budget",
        "Total Actual",
        "Total Variance",
        "Variance %",
        "Potential Savings",
        "Opportunities",
        "Depts Over Budget",
        "Transactions",
    ):
        assert caption in html
    assert compact_money(kpis["total_budget"]) in html


def test_build_dashboard_html_contains_charts() -> None:
    _, dept_summary, opportunities, monthly_trend, kpis = _pipeline_outputs()
    html = html_dashboard.build_dashboard_html(
        dept_summary, opportunities, monthly_trend, kpis, year=2025
    )
    for title in (
        "Budget vs. Actual by Department",
        "Actual Spend Mix by Department",
        "Monthly Budget vs. Actual Spend",
        "Department Variance vs. Budget",
        "Budget Utilisation",
    ):
        assert title in html
    # 4 charts + the utilisation gauge
    assert html.count('class="plotly-graph-div"') == 5
    # plotly.js inlined → self-contained file in the MB range
    assert len(html) > 1_000_000


def test_build_dashboard_html_contains_interactive_scaffolding() -> None:
    df, dept_summary, opportunities, monthly_trend, kpis = _pipeline_outputs()
    html = html_dashboard.build_dashboard_html(
        dept_summary, opportunities, monthly_trend, kpis, year=2025, df=df
    )
    assert 'id="opex-data"' in html
    assert '"hasTx": true' in html
    assert 'class="chip on"' in html
    assert "data-target=" in html
    assert 'class="tabs"' in html
    assert "data-drill" in html
    for div_id in ("fig-budget", "fig-mix", "fig-monthly", "fig-variance", "fig-gauge"):
        assert f'id="{div_id}"' in html


def test_write_dashboard_creates_file() -> None:
    df, dept_summary, opportunities, monthly_trend, kpis = _pipeline_outputs()
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        html_dashboard.write_dashboard(
            df, dept_summary, opportunities, monthly_trend, kpis, output_file=tmp_path
        )
        assert os.path.getsize(tmp_path) > 0
        with open(tmp_path, encoding="utf-8") as handle:
            content = handle.read()
        assert "<html" in content
        assert "RED BULL RACING" in content
    finally:
        os.unlink(tmp_path)


def test_write_dashboard_handles_no_opportunities() -> None:
    df, dept_summary, _, monthly_trend, _ = _pipeline_outputs(inject=False)
    kpis = analysis.compute_kpis(df, [])
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        html_dashboard.write_dashboard(
            df, dept_summary, [], monthly_trend, kpis, output_file=tmp_path
        )
        with open(tmp_path, encoding="utf-8") as handle:
            content = handle.read()
        assert "No opportunities flagged" in content
    finally:
        os.unlink(tmp_path)

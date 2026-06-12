import os
import re
import tempfile
import zipfile

import pandas as pd
import pytest

import analysis
import data_generator
import excel_reporter
import exceptions


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Date": "2025-01-05",
                "Department": "Aerodynamics",
                "Expense Type": "CFD License",
                "Vendor": "Vendor A",
                "Description": "Parts",
                "Budgeted Amount": 10000,
                "Actual Amount": 17000,
            },
            {
                "Date": "2025-01-05",
                "Department": "Aerodynamics",
                "Expense Type": "CFD License",
                "Vendor": "Vendor A",
                "Description": "Parts",
                "Budgeted Amount": 10000,
                "Actual Amount": 17000,
            },
            {
                "Date": "2025-01-06",
                "Department": "Logistics",
                "Expense Type": "Freight - Air",
                "Vendor": "Vendor B",
                "Description": "Shipping",
                "Budgeted Amount": 20000,
                "Actual Amount": 19000,
            },
        ]
    )


def test_calculate_variance_adds_columns(sample_df: pd.DataFrame) -> None:
    result = analysis.calculate_variance(sample_df)
    assert "Variance" in result.columns
    assert "Variance %" in result.columns
    assert result.loc[0, "Variance"] == 7000
    assert result.loc[0, "Variance %"] == pytest.approx(0.7)


def test_analyze_department_spending_rollup(sample_df: pd.DataFrame) -> None:
    df = analysis.calculate_variance(sample_df)
    result = analysis.analyze_department_spending(df)
    aero = result[result["Department"] == "Aerodynamics"].iloc[0]
    assert aero["Budgeted Amount"] == 20000
    assert aero["Actual Amount"] == 34000
    assert aero["Variance"] == 14000
    assert aero["Variance %"] == pytest.approx(0.7)


def test_identify_savings_opportunities(sample_df: pd.DataFrame) -> None:
    df = analysis.calculate_variance(sample_df)
    opportunities = analysis.identify_savings_opportunities(df)
    types = {item["Type"] for item in opportunities}
    assert "High Variance Outlier" in types
    assert "Potential Duplicate Payments" in types


def test_unbudgeted_overspend_is_flagged() -> None:
    df = pd.DataFrame(
        [
            {
                "Date": "2025-01-07",
                "Department": "IT",
                "Expense Type": "Hardware Upgrades",
                "Vendor": "Vendor C",
                "Description": "Emergency purchase",
                "Budgeted Amount": 0,
                "Actual Amount": 12000,
            }
        ]
    )
    df = analysis.calculate_variance(df)
    opportunities = analysis.identify_savings_opportunities(df)
    assert "High Variance Outlier" in {item["Type"] for item in opportunities}


def test_date_range_bounds() -> None:
    df = data_generator.generate_opex_data(num_records=500, year=2024, seed=42)
    dates = pd.to_datetime(df["Date"])
    assert dates.min() >= pd.Timestamp("2024-01-01")
    assert dates.max() <= pd.Timestamp("2024-12-31")


def test_inject_anomalies_false_produces_clean_data() -> None:
    df = data_generator.generate_opex_data(num_records=10, seed=42, inject_anomalies=False)
    assert len(df) == 10
    assert not df.duplicated(subset=["Date", "Vendor", "Department", "Expense Type"]).any()


def test_compute_monthly_trend_shape() -> None:
    df = data_generator.generate_opex_data(num_records=500, year=2025, seed=7)
    trend = analysis.compute_monthly_trend(df)
    assert "Month Name" in trend.columns
    assert "Budgeted Amount" in trend.columns
    assert "Actual Amount" in trend.columns
    assert len(trend) == 12
    assert list(trend["Month Name"]) == [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    assert (trend["Budgeted Amount"] >= 0).all()
    assert (trend["Actual Amount"] >= 0).all()


def test_data_generation_error_on_too_few_records() -> None:
    with pytest.raises(exceptions.DataGenerationError):
        data_generator.generate_opex_data(num_records=0, inject_anomalies=True)


def test_excel_report_creates_file() -> None:
    df = data_generator.generate_opex_data(num_records=50, seed=1)
    df = analysis.calculate_variance(df)
    dept_summary = analysis.analyze_department_spending(df)
    opportunities = analysis.identify_savings_opportunities(df)
    monthly_trend = analysis.compute_monthly_trend(df)
    kpis = analysis.compute_kpis(df, opportunities)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        excel_reporter.create_excel_report(
            df, dept_summary, opportunities, monthly_trend, kpis, output_file=tmp_path
        )
        assert os.path.isfile(tmp_path)
        assert os.path.getsize(tmp_path) > 0

        with zipfile.ZipFile(tmp_path) as z:
            wb_xml = z.read("xl/workbook.xml").decode()
            sheets = re.findall(r'<sheet name="([^"]+)"', wb_xml)
            charts = [n for n in z.namelist() if n.startswith("xl/charts/")]

        assert sheets == [
            "Dashboard",
            "Executive Summary",
            "Savings Opportunities",
            "Monthly Trends",
            "Detailed Data",
        ]
        assert len(charts) == 7, f"Expected 7 charts, found {len(charts)}: {charts}"
    finally:
        os.unlink(tmp_path)


def test_monthly_trend_fills_missing_months() -> None:
    df = pd.DataFrame(
        [
            {
                "Date": "2025-01-15",
                "Department": "IT",
                "Expense Type": "Software Licenses",
                "Vendor": "Oracle",
                "Description": "License",
                "Budgeted Amount": 1000.0,
                "Actual Amount": 900.0,
            }
        ]
    )
    trend = analysis.compute_monthly_trend(df)
    assert len(trend) == 12
    assert (trend["Budgeted Amount"] >= 0).all()
    assert (trend["Actual Amount"] >= 0).all()
    jan = trend[trend["Month Name"] == "Jan"].iloc[0]
    assert jan["Budgeted Amount"] == 1000.0
    feb = trend[trend["Month Name"] == "Feb"].iloc[0]
    assert feb["Budgeted Amount"] == 0.0
    assert feb["Actual Amount"] == 0.0


def test_duplicate_detection_uses_semantic_key() -> None:
    df_dup = pd.DataFrame(
        [
            {
                "Date": "2025-03-01",
                "Department": "IT",
                "Expense Type": "Software Licenses",
                "Vendor": "Oracle",
                "Description": "License A",
                "Budgeted Amount": 5000.0,
                "Actual Amount": 5000.0,
            },
            {
                "Date": "2025-03-01",
                "Department": "IT",
                "Expense Type": "Software Licenses",
                "Vendor": "Oracle",
                "Description": "License B",
                "Budgeted Amount": 5000.0,
                "Actual Amount": 5100.0,
            },
        ]
    )
    df_dup = analysis.calculate_variance(df_dup)
    opps = analysis.identify_savings_opportunities(df_dup)
    assert any(o["Type"] == "Potential Duplicate Payments" for o in opps)

    df_no_dup = pd.DataFrame(
        [
            {
                "Date": "2025-03-01",
                "Department": "IT",
                "Expense Type": "Software Licenses",
                "Vendor": "Oracle",
                "Description": "License A",
                "Budgeted Amount": 5000.0,
                "Actual Amount": 5000.0,
            },
            {
                "Date": "2025-03-01",
                "Department": "Aerodynamics",
                "Expense Type": "CFD License",
                "Vendor": "Oracle",
                "Description": "License B",
                "Budgeted Amount": 5000.0,
                "Actual Amount": 5000.0,
            },
        ]
    )
    df_no_dup = analysis.calculate_variance(df_no_dup)
    opps_no_dup = analysis.identify_savings_opportunities(df_no_dup)
    assert not any(o["Type"] == "Potential Duplicate Payments" for o in opps_no_dup)


def test_empty_opportunities_renders() -> None:
    df = data_generator.generate_opex_data(num_records=50, seed=1)
    df = analysis.calculate_variance(df)
    dept_summary = analysis.analyze_department_spending(df)
    monthly_trend = analysis.compute_monthly_trend(df)
    kpis = analysis.compute_kpis(df, [])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        excel_reporter.create_excel_report(
            df, dept_summary, [], monthly_trend, kpis, output_file=tmp_path
        )
        assert os.path.isfile(tmp_path)
        assert os.path.getsize(tmp_path) > 0
    finally:
        os.unlink(tmp_path)


def test_department_expense_type_consistency() -> None:
    from data_generator import DEPARTMENTS, EXPENSE_TYPES

    assert set(DEPARTMENTS) == set(EXPENSE_TYPES.keys())


def test_compute_kpis_totals_and_variance(sample_df: pd.DataFrame) -> None:
    df = analysis.calculate_variance(sample_df)
    kpis = analysis.compute_kpis(df, [])
    # sample_df: budget 10k+10k+20k = 40k, actual 17k+17k+19k = 53k
    assert kpis["total_budget"] == pytest.approx(40000.0)
    assert kpis["total_actual"] == pytest.approx(53000.0)
    assert kpis["total_variance"] == pytest.approx(13000.0)
    assert kpis["variance_pct"] == pytest.approx(13000.0 / 40000.0)
    assert kpis["num_transactions"] == 3
    # Aerodynamics is over budget (+14k), Logistics under (-1k)
    assert kpis["departments_over_budget"] == 1


def test_compute_kpis_aggregates_savings(sample_df: pd.DataFrame) -> None:
    df = analysis.calculate_variance(sample_df)
    opportunities = analysis.identify_savings_opportunities(df)
    kpis = analysis.compute_kpis(df, opportunities)
    assert kpis["num_opportunities"] == len(opportunities)
    assert kpis["potential_savings"] == pytest.approx(
        sum(o["Potential Savings"] for o in opportunities)
    )


def test_compute_kpis_handles_empty_opportunities(sample_df: pd.DataFrame) -> None:
    df = analysis.calculate_variance(sample_df)
    kpis = analysis.compute_kpis(df, [])
    assert kpis["num_opportunities"] == 0
    assert kpis["potential_savings"] == 0.0

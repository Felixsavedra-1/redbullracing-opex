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


def test_load_data_parses_date_type(sample_df: pd.DataFrame) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        sample_df.to_csv(tmp.name, index=False)
        tmp_path = tmp.name
    try:
        loaded = analysis.load_data(tmp_path)
        assert pd.api.types.is_datetime64_any_dtype(loaded["Date"])
    finally:
        os.unlink(tmp_path)


def test_date_range_bounds() -> None:
    df = data_generator.generate_opex_data(num_records=500, year=2024, seed=42)
    dates = pd.to_datetime(df["Date"])
    assert dates.min() >= pd.Timestamp("2024-01-01")
    assert dates.max() <= pd.Timestamp("2024-12-31")


def test_inject_anomalies_false_produces_clean_data() -> None:
    df = data_generator.generate_opex_data(num_records=10, seed=42, inject_anomalies=False)
    assert len(df) == 10
    assert not df.duplicated(subset=["Date", "Vendor", "Actual Amount"]).any()


def test_load_data_raises_on_missing_columns() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
        pd.DataFrame([{"wrong_col": 1}]).to_csv(tmp.name, index=False)
        tmp_path = tmp.name
    try:
        with pytest.raises(exceptions.ValidationError):
            analysis.load_data(tmp_path)
    finally:
        os.unlink(tmp_path)


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


def test_data_generation_error_on_too_few_records() -> None:
    with pytest.raises(exceptions.DataGenerationError):
        data_generator.generate_opex_data(num_records=2, inject_anomalies=True)


def test_excel_report_creates_file() -> None:
    df = data_generator.generate_opex_data(num_records=50, seed=1)
    df = analysis.calculate_variance(df)
    dept_summary = analysis.analyze_department_spending(df)
    opportunities = analysis.identify_savings_opportunities(df)
    monthly_trend = analysis.compute_monthly_trend(df)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        excel_reporter.create_excel_report(
            df, dept_summary, opportunities, monthly_trend, output_file=tmp_path
        )
        assert os.path.isfile(tmp_path)
        assert os.path.getsize(tmp_path) > 0

        with zipfile.ZipFile(tmp_path) as z:
            wb_xml = z.read("xl/workbook.xml").decode()
            sheets = re.findall(r'<sheet name="([^"]+)"', wb_xml)
            charts = [n for n in z.namelist() if n.startswith("xl/charts/")]

        assert sheets == [
            "Executive Summary",
            "Savings Opportunities",
            "Monthly Trends",
            "Detailed Data",
        ]
        assert len(charts) == 4, f"Expected 4 charts, found {len(charts)}: {charts}"
    finally:
        os.unlink(tmp_path)

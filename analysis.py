from __future__ import annotations

import calendar
from typing import Any, TypedDict, cast

import pandas as pd

from constants import HIGH_VARIANCE_AMOUNT, HIGH_VARIANCE_PCT
from exceptions import ValidationError

_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "Date",
        "Department",
        "Expense Type",
        "Vendor",
        "Description",
        "Budgeted Amount",
        "Actual Amount",
    }
)

# Composite key that identifies a payment — exact match on all three = likely duplicate
_DUPLICATE_PAYMENT_KEYS: tuple[str, ...] = ("Date", "Vendor", "Actual Amount")

Opportunity = TypedDict(
    "Opportunity",
    {
        "Type": str,
        "Count": int,
        "Potential Savings": float,
        "Details": list[dict[str, Any]],
    },
)


def _validate_columns(df: pd.DataFrame, required: frozenset[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValidationError(f"DataFrame missing required columns: {sorted(missing)}")


def _safe_divide(numerator: pd.Series[float], denominator: pd.Series[float]) -> pd.Series[float]:
    """Divide with zero protection, returning 0 when denominator is 0."""
    return (numerator / denominator.replace(0, float("nan"))).fillna(0.0)


def load_data(filepath: str) -> pd.DataFrame:
    """Load OPEX data from CSV and validate required columns are present."""
    df = pd.read_csv(filepath)
    _validate_columns(df, _REQUIRED_COLUMNS)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


def calculate_variance(df: pd.DataFrame) -> pd.DataFrame:
    """Add absolute and percentage variance columns."""
    _validate_columns(df, frozenset({"Budgeted Amount", "Actual Amount"}))
    df = df.copy()
    variance = df["Actual Amount"] - df["Budgeted Amount"]
    df["Variance"] = variance
    df["Variance %"] = _safe_divide(variance, df["Budgeted Amount"])
    return df


def analyze_department_spending(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate spending and variance by department."""
    _validate_columns(df, frozenset({"Department", "Budgeted Amount", "Actual Amount", "Variance"}))
    grouped = df.groupby("Department", as_index=False).agg(
        {"Budgeted Amount": "sum", "Actual Amount": "sum", "Variance": "sum"}
    )
    grouped["Variance %"] = _safe_divide(grouped["Variance"], grouped["Budgeted Amount"])
    return grouped.sort_values("Variance", ascending=False, ignore_index=True)


def compute_monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate budget and actual spend by calendar month."""
    _validate_columns(df, frozenset({"Date", "Budgeted Amount", "Actual Amount"}))
    month_names = [calendar.month_abbr[m] for m in range(1, 13)]
    monthly = (
        df.assign(Month=pd.to_datetime(df["Date"]).dt.month)
        .groupby("Month", as_index=False)
        .agg({"Budgeted Amount": "sum", "Actual Amount": "sum"})
        .sort_values("Month")
    )
    monthly["Month Name"] = monthly["Month"].apply(lambda m: month_names[int(m) - 1])
    return monthly[["Month Name", "Budgeted Amount", "Actual Amount"]].reset_index(drop=True)


def identify_savings_opportunities(df: pd.DataFrame) -> list[Opportunity]:
    """Flag large overspends and duplicate payments."""
    opportunities: list[Opportunity] = []

    overspend_mask = (df["Budgeted Amount"] > 0) & (df["Variance %"] > HIGH_VARIANCE_PCT)
    unbudgeted_mask = (df["Budgeted Amount"] == 0) & (df["Variance"] > 0)
    high_variance = df[(overspend_mask | unbudgeted_mask) & (df["Variance"] > HIGH_VARIANCE_AMOUNT)]
    if not high_variance.empty:
        opportunities.append(
            {
                "Type": "High Variance Outlier",
                "Count": len(high_variance),
                "Potential Savings": float(high_variance["Variance"].sum()),
                "Details": cast(
                    list[dict[str, Any]],
                    high_variance[["Date", "Department", "Description", "Variance"]].to_dict(
                        "records"
                    ),
                ),
            }
        )

    duplicates = df[df.duplicated(subset=list(_DUPLICATE_PAYMENT_KEYS), keep=False)]
    if not duplicates.empty:
        dup_groups = duplicates.groupby(list(_DUPLICATE_PAYMENT_KEYS))["Actual Amount"]
        excess_count = int((dup_groups.size() - 1).sum())
        excess_savings = float((dup_groups.sum() - dup_groups.max()).sum())
        opportunities.append(
            {
                "Type": "Potential Duplicate Payments",
                "Count": excess_count,
                "Potential Savings": excess_savings,
                "Details": cast(
                    list[dict[str, Any]],
                    duplicates[["Date", "Vendor", "Description", "Actual Amount"]].to_dict(
                        "records"
                    ),
                ),
            }
        )

    return opportunities

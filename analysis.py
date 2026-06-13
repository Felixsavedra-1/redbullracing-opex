from __future__ import annotations

import calendar
from typing import Any, TypedDict, cast

import pandas as pd

from constants import HIGH_VARIANCE_AMOUNT, HIGH_VARIANCE_PCT
from exceptions import ValidationError

_DUPLICATE_PAYMENT_KEYS: list[str] = ["Date", "Vendor", "Department", "Expense Type"]

Opportunity = TypedDict(
    "Opportunity",
    {
        "Type": str,
        "Count": int,
        "Potential Savings": float,
        "Details": list[dict[str, Any]],
    },
)


class KpiSummary(TypedDict):
    total_budget: float
    total_actual: float
    total_variance: float
    variance_pct: float
    num_transactions: int
    departments_over_budget: int
    potential_savings: float
    num_opportunities: int


def _validate_columns(df: pd.DataFrame, required: frozenset[str]) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValidationError(f"DataFrame missing required columns: {sorted(missing)}")


def _safe_divide(numerator: pd.Series[float], denominator: pd.Series[float]) -> pd.Series[float]:
    return (numerator / denominator.replace(0, float("nan"))).fillna(0.0)


def calculate_variance(df: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(df, frozenset({"Budgeted Amount", "Actual Amount"}))
    df = df.copy()
    variance = df["Actual Amount"] - df["Budgeted Amount"]
    df["Variance"] = variance
    df["Variance %"] = _safe_divide(variance, df["Budgeted Amount"])
    return df


def analyze_department_spending(df: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(df, frozenset({"Department", "Budgeted Amount", "Actual Amount", "Variance"}))
    grouped = df.groupby("Department", as_index=False).agg(
        {"Budgeted Amount": "sum", "Actual Amount": "sum", "Variance": "sum"}
    )
    grouped["Variance %"] = _safe_divide(grouped["Variance"], grouped["Budgeted Amount"])
    return grouped.sort_values("Variance", ascending=False, ignore_index=True)


def compute_kpis(df: pd.DataFrame, opportunities: list[Opportunity]) -> KpiSummary:
    _validate_columns(df, frozenset({"Department", "Budgeted Amount", "Actual Amount", "Variance"}))
    total_budget = float(df["Budgeted Amount"].sum())
    total_actual = float(df["Actual Amount"].sum())
    total_variance = total_actual - total_budget
    dept_variance = df.groupby("Department")["Variance"].sum()
    return KpiSummary(
        total_budget=total_budget,
        total_actual=total_actual,
        total_variance=total_variance,
        variance_pct=total_variance / total_budget if total_budget else 0.0,
        num_transactions=int(len(df)),
        departments_over_budget=int((dept_variance > 0).sum()),
        potential_savings=float(sum(opp["Potential Savings"] for opp in opportunities)),
        num_opportunities=len(opportunities),
    )


def compute_monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(df, frozenset({"Date", "Budgeted Amount", "Actual Amount"}))
    month_names = [calendar.month_abbr[m] for m in range(1, 13)]
    grouped = (
        df.assign(Month=pd.to_datetime(df["Date"]).dt.month)
        .groupby("Month", as_index=False)
        .agg({"Budgeted Amount": "sum", "Actual Amount": "sum"})
    )
    all_months = pd.DataFrame({"Month": range(1, 13)})
    monthly = all_months.merge(grouped, on="Month", how="left").fillna(0.0)
    monthly["Month Name"] = monthly["Month"].apply(lambda m: month_names[int(m) - 1])
    return monthly[["Month Name", "Budgeted Amount", "Actual Amount"]].reset_index(drop=True)


def identify_savings_opportunities(df: pd.DataFrame) -> list[Opportunity]:
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

    duplicates = df[df.duplicated(subset=_DUPLICATE_PAYMENT_KEYS, keep=False)]
    if not duplicates.empty:
        dup_groups = duplicates.groupby(_DUPLICATE_PAYMENT_KEYS)["Actual Amount"]
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

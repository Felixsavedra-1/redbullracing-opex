from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from constants import (
    ACTUAL_MEAN_RATIO,
    ACTUAL_STD_RATIO,
    ACTUAL_UPPER_CAP,
    ANOMALY_ACTUAL,
    ANOMALY_BUDGET,
    BUDGET_MAX,
    BUDGET_MIN,
)
from exceptions import DataGenerationError

DEPARTMENTS: list[str] = [
    "Aerodynamics",
    "Power Unit",
    "Chassis",
    "Logistics",
    "Strategy",
    "Vehicle Performance",
    "Marketing",
    "IT",
]

EXPENSE_TYPES: dict[str, list[str]] = {
    "Aerodynamics": ["Wind Tunnel Usage", "CFD License", "Composite Materials", "Prototyping"],
    "Power Unit": [
        "Engine Testing",
        "Fuel Analysis",
        "Hybrid System Components",
        "Dyno Operations",
    ],
    "Chassis": ["Carbon Fiber", "Suspension Parts", "Crash Testing", "Machining"],
    "Logistics": ["Freight - Air", "Freight - Sea", "Travel & Accommodation", "Catering"],
    "Strategy": ["Simulation Software", "Data Feeds", "Consulting", "Compute Resources"],
    "Vehicle Performance": [
        "Telemetry Systems",
        "Trackside Equipment",
        "Sensor Calibration",
        "Driver Simulator",
    ],
    "Marketing": ["Sponsorship Events", "Merchandise", "Digital Content", "Hospitality"],
    "IT": ["Server Infrastructure", "Cybersecurity", "Software Licenses", "Hardware Upgrades"],
}

VENDORS: list[str] = [
    "Oracle",
    "Honda",
    "Siemens",
    "Hewlett Packard Enterprise",
    "AT&T",
    "Tag Heuer",
    "Mobil 1",
    "Pirelli",
    "DHL",
    "Ansys",
]

_extra = set(EXPENSE_TYPES) - set(DEPARTMENTS)
_missing = set(DEPARTMENTS) - set(EXPENSE_TYPES)
if _extra or _missing:
    raise DataGenerationError(
        f"EXPENSE_TYPES/DEPARTMENTS mismatch — extra: {_extra}, missing: {_missing}"
    )


def _inject_demo_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    source = df.iloc[0].copy()

    overspend = source.copy()
    overspend["Department"] = "Logistics"
    overspend["Expense Type"] = "Freight - Air"
    overspend["Budgeted Amount"] = ANOMALY_BUDGET
    overspend["Actual Amount"] = ANOMALY_ACTUAL
    overspend["Description"] = "Emergency Air Freight - Urgent Upgrade Package"

    duplicate = source.copy()
    duplicate["Description"] = f"{source['Description']} (DUPLICATE?)"

    return pd.concat([df, pd.DataFrame([overspend, duplicate])], ignore_index=True)


def generate_opex_data(
    num_records: int = 500,
    year: int = 2025,
    seed: int | None = 42,
    inject_anomalies: bool = True,
) -> pd.DataFrame:
    if inject_anomalies and num_records < 1:
        raise DataGenerationError("num_records must be at least 1 to inject demo anomalies.")

    rng = np.random.default_rng(seed)
    start_date = datetime(year, 1, 1)
    days_in_year = (datetime(year + 1, 1, 1) - start_date).days

    dept_indices = rng.integers(0, len(DEPARTMENTS), size=num_records)
    depts = [DEPARTMENTS[int(i)] for i in dept_indices]
    expenses = [rng.choice(EXPENSE_TYPES[dept]) for dept in depts]
    vendor_indices = rng.integers(0, len(VENDORS), size=num_records)
    vendors = [VENDORS[int(i)] for i in vendor_indices]

    day_offsets = rng.integers(0, days_in_year, size=num_records)
    dates = [start_date + timedelta(days=int(d)) for d in day_offsets]

    budgets = np.round(rng.uniform(BUDGET_MIN, BUDGET_MAX, size=num_records), 2)
    raw_actuals = budgets * rng.normal(ACTUAL_MEAN_RATIO, ACTUAL_STD_RATIO, size=num_records)
    actuals = np.round(np.clip(raw_actuals, 0.0, budgets * ACTUAL_UPPER_CAP), 2)

    df = pd.DataFrame(
        {
            "Date": dates,
            "Department": depts,
            "Expense Type": expenses,
            "Vendor": vendors,
            "Description": [f"{e} invoice from {v}" for e, v in zip(expenses, vendors)],
            "Budgeted Amount": budgets,
            "Actual Amount": actuals,
        }
    )

    if inject_anomalies:
        df = _inject_demo_anomalies(df)
    return df

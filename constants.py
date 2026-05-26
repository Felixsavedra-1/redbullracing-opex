# ── Data generation ──────────────────────────────────────────────────────────
BUDGET_MIN: float = 1_000.0
BUDGET_MAX: float = 100_000.0
ACTUAL_MEAN_RATIO: float = 1.0  # normal distribution center (1.0 = on-budget)
ACTUAL_STD_RATIO: float = 0.15  # spread around budget
ACTUAL_UPPER_CAP: float = 5.0  # hard ceiling: actual ≤ 5× budget
ANOMALY_BUDGET: float = 50_000.0
ANOMALY_ACTUAL: float = 120_000.0  # 240 % overspend — intentional demo outlier

# ── Analysis thresholds ──────────────────────────────────────────────────────
HIGH_VARIANCE_PCT: float = 0.50  # flag overspends > 50 % above budget
HIGH_VARIANCE_AMOUNT: float = 5_000.0  # absolute floor — suppresses small-item noise

# ── CLI defaults ─────────────────────────────────────────────────────────────
DEFAULT_RECORDS: int = 500
DEFAULT_YEAR: int = 2025
DEFAULT_SEED: int = 42

# ── Report formatting ─────────────────────────────────────────────────────────
COLOR_HEADER_BG: str = "#D3D3D3"
COLOR_OVERSPEND_BG: str = "#FFC7CE"
COLOR_OVERSPEND_FG: str = "#9C0006"
COLOR_SAVING_BG: str = "#C6EFCE"
COLOR_SAVING_FG: str = "#006100"
COLOR_RB_BLUE: str = "#3671C6"  # Red Bull Racing primary blue
COLOR_RB_RED: str = "#E8002D"  # Red Bull Racing primary red
VARIANCE_FLAG_THRESHOLD: float = 0.10  # flag > 10 % overspend for finance review
TOP_EXPENSE_TYPES: int = 10  # expense-type breakdown chart: show this many rows

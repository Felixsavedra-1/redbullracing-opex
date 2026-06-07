# Data generation
BUDGET_MIN: float = 1_000.0
BUDGET_MAX: float = 100_000.0
ACTUAL_MEAN_RATIO: float = 1.0  # distribution center: 1.0 == on-budget
ACTUAL_STD_RATIO: float = 0.15
ACTUAL_UPPER_CAP: float = 5.0  # actual is capped at 5x budget
ANOMALY_BUDGET: float = 50_000.0
ANOMALY_ACTUAL: float = 120_000.0  # 240% overspend — intentional demo outlier

# Analysis thresholds
HIGH_VARIANCE_PCT: float = 0.50  # overspend flag: >50% above budget
HIGH_VARIANCE_AMOUNT: float = 5_000.0  # absolute floor suppresses small-item noise

# CLI defaults
DEFAULT_RECORDS: int = 500
DEFAULT_YEAR: int = 2025
DEFAULT_SEED: int = 42

# Excel report formatting
COLOR_HEADER_BG: str = "#D3D3D3"
COLOR_OVERSPEND_BG: str = "#FFC7CE"
COLOR_OVERSPEND_FG: str = "#9C0006"
COLOR_SAVING_BG: str = "#C6EFCE"
COLOR_SAVING_FG: str = "#006100"
COLOR_RB_BLUE: str = "#3671C6"
COLOR_RB_RED: str = "#E8002D"
VARIANCE_FLAG_THRESHOLD: float = 0.10  # flag >10% overspend for finance review
TOP_EXPENSE_TYPES: int = 10

# Excel dashboard cockpit
COLOR_RB_NAVY: str = "#121F45"
COLOR_RB_YELLOW: str = "#FFC906"
COLOR_CARD_BG: str = "#F2F4F8"
COLOR_CARD_FG: str = "#121F45"
COLOR_MUTED_FG: str = "#6B7280"
COLOR_WHITE: str = "#FFFFFF"

# Interactive HTML dashboard (black / bone-white / crimson theme)
COLOR_DASH_BG: str = "#000000"
COLOR_DASH_SURFACE: str = "#15171A"  # charcoal-tinted surface (hover tooltips, depth)
COLOR_DASH_FG: str = "#ECE5D5"  # bone white
COLOR_DASH_MUTED: str = "#8C857A"  # warm bone-grey
COLOR_DASH_GRID: str = "#211C1A"  # warm near-black hairline
COLOR_DASH_TAN: str = "#C7A06A"  # warm sand-gold accent (donut variety, neutral KPI tiles)
COLOR_DASH_TITANIUM: str = "#9DA3A8"  # cool metallic grey (Budget series + under-budget/good)
COLOR_DASH_CHARCOAL: str = "#2B2E33"  # charcoal grey for panel surface depth
COLOR_POSITIVE: str = COLOR_DASH_TITANIUM  # under budget / savings (titanium grey)
COLOR_NEGATIVE: str = "#D6203F"  # over budget (bright crimson)
COLOR_DASH_CRIMSON: str = "#B3122B"  # deep brand crimson: chrome, "Actual" fills, donut darkest
COLOR_DASH_GLOW: str = "rgba(179,18,43,0.45)"  # crimson glow
COLOR_DASH_NEON: str = "#D6203F"  # bright crimson highlight (active/hover)
COLOR_DASH_SCAN: str = "rgba(214,32,63,0.06)"  # crimson scanline tint
DASH_FONT: str = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"

def compact_money(value: float) -> str:
    """Render a currency figure as a compact KPI string ($1.2M / $340K / $920)."""
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"${value / 1_000_000:,.1f}M"
    if magnitude >= 1_000:
        return f"${value / 1_000:,.0f}K"
    return f"${value:,.0f}"

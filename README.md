# Red Bull Racing F1 — OPEX Analysis Pipeline

Python pipeline for F1 operational expenditure analysis: variance detection, savings identification, and executive-ready Excel reporting.

## Overview

Formula 1 teams manage complex, multi-department budgets across hundreds of monthly transactions. This pipeline ingests (or generates) OPEX data, flags overspends and duplicate payments, and produces a formatted 4-sheet Excel workbook with embedded charts — built to surface cost visibility at the department level.

## Output

| Sheet | Contents |
|---|---|
| Executive Summary | Department spend vs. budget · Budget vs Actual and Variance % column charts · red/green conditional formatting |
| Savings Opportunities | High-variance outliers (>50% + $5K threshold) · duplicate payment groups · total potential savings |
| Monthly Trends | Budget vs actual line chart · top 10 expense types horizontal bar chart |
| Detailed Data | Full transaction table · currency and percentage formatting · frozen header |

## Quick Start

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Default: 500 synthetic records, year 2025, seed 42, report written to `opex_analysis_report.xlsx`.

## Run

```bash
python3 main.py [--records 500] [--year 2025] [--seed 42] [--no-anomalies] [--verbose]
```

```
09:01:12 [INFO] Generating 500 synthetic records for 2025…
09:01:12 [INFO] Running variance analysis…
09:01:12 [INFO] Found 8 department(s), 2 savings opportunities
09:01:12 [INFO] Report written → opex_analysis_report.xlsx
```

## Test

```bash
pytest -v   # 11 tests
```

## Architecture

```
main.py            CLI orchestrator — arg parsing, logging, per-step timing
data_generator.py  Synthetic OPEX transactions → DataFrame (seeded, reproducible)
constants.py       Single source of truth for all thresholds, colors, and defaults
exceptions.py      Typed exception hierarchy: OpexError → DataGenerationError | ValidationError | ReportError
analysis.py        Variance metrics, department rollup, monthly trends, savings detection
excel_reporter.py  4-sheet .xlsx workbook with conditional formatting and 4 charts
```

Data flows in one direction:

```
generate_opex_data()
  → calculate_variance()
  → analyze_department_spending() + identify_savings_opportunities() + compute_monthly_trend()
  → create_excel_report()
  → opex_analysis_report.xlsx
```

## Engineering

- **Typed end-to-end** — `TypedDict` for all pipeline outputs, `cast()` for pandas interop, `mypy --strict` with zero suppressions; type errors surface at development time, not runtime
- **Custom exception hierarchy** — `OpexError` base with typed subclasses; expected failures exit 1, unexpected crashes exit 2, so callers can distinguish recoverable errors from bugs
- **Centralized constants** — all thresholds, colors, and defaults in `constants.py`; changing a detection threshold is a one-line edit with no grep required
- **Vectorized RNG** — `numpy.random.default_rng(seed)` makes every synthetic dataset fully reproducible across platforms and Python versions
- **Fail-fast column validation** — `_validate_columns()` guards every pipeline stage before any computation runs; bad data is rejected at the boundary, not mid-aggregation
- **Per-step timing** — `TimerContext` context manager profiles each phase without cluttering business logic; visible with `--verbose`
- **11 tests** — variance math, rollup correctness, anomaly detection, date bounds, schema validation, Excel structure verified via `zipfile`

## Stack

Python 3.11 · pandas · numpy · xlsxwriter · pytest · mypy (strict) · ruff

---

<p align="center">
  <img src="company.JPG" width="50%" alt="Red Bull Racing" />
</p>

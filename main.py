import argparse
import logging
import sys
import time

import analysis
import data_generator
import excel_reporter
import html_dashboard
from constants import DEFAULT_RECORDS, DEFAULT_SEED, DEFAULT_YEAR
from exceptions import OpexError

_logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the F1 OPEX analysis pipeline.")
    parser.add_argument(
        "--records", type=int, default=DEFAULT_RECORDS, help="Number of records to generate."
    )
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help="Year to simulate.")
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Random seed for reproducible data generation.",
    )
    parser.add_argument(
        "--csv-path", default="opex_data.csv", help="Where to write the generated CSV."
    )
    parser.add_argument(
        "--report-path",
        default="opex_analysis_report.xlsx",
        help="Where to write the Excel report.",
    )
    parser.add_argument(
        "--html-path",
        default="f1opex_dashboard.html",
        help="Where to write the interactive HTML dashboard.",
    )
    parser.add_argument(
        "--no-html", action="store_true", help="Skip the interactive HTML dashboard."
    )
    parser.add_argument(
        "--no-anomalies", action="store_true", help="Disable injected demo anomalies."
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG-level logging.")
    args = parser.parse_args()
    if args.records < 1:
        parser.error("--records must be a positive integer")
    if args.year < 1900 or args.year > 2100:
        parser.error("--year must be between 1900 and 2100")
    return args


class TimerContext:
    def __init__(self, label: str) -> None:
        self._label = label
        self._start = 0.0

    def __enter__(self) -> "TimerContext":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_: object) -> None:
        elapsed = time.perf_counter() - self._start
        _logger.debug("%s completed in %.3fs", self._label, elapsed)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        with TimerContext("data generation"):
            _logger.info("Generating %d synthetic records for %d…", args.records, args.year)
            df = data_generator.generate_opex_data(
                num_records=args.records,
                year=args.year,
                seed=args.seed,
                inject_anomalies=not args.no_anomalies,
            )
            df.to_csv(args.csv_path, index=False)
            _logger.info("Data written → %s", args.csv_path)

        with TimerContext("variance analysis"):
            _logger.info("Running variance analysis…")
            df = analysis.calculate_variance(df)
            dept_summary = analysis.analyze_department_spending(df)
            opportunities = analysis.identify_savings_opportunities(df)
            monthly_trend = analysis.compute_monthly_trend(df)
            kpis = analysis.compute_kpis(df, opportunities)
            _logger.info(
                "Found %d department(s), %d savings opportunities, %.1f%% total variance",
                len(dept_summary),
                len(opportunities),
                kpis["variance_pct"] * 100,
            )

        with TimerContext("report generation"):
            _logger.info("Building Excel report…")
            excel_reporter.create_excel_report(
                df,
                dept_summary,
                opportunities,
                monthly_trend,
                kpis,
                output_file=args.report_path,
                year=args.year,
            )
            _logger.info("Report written → %s", args.report_path)

            if not args.no_html:
                html_dashboard.write_dashboard(
                    df,
                    dept_summary,
                    opportunities,
                    monthly_trend,
                    kpis,
                    output_file=args.html_path,
                    year=args.year,
                )
                _logger.info("HTML dashboard written → %s", args.html_path)

    except OpexError as exc:
        _logger.error("Pipeline error: %s", exc)
        sys.exit(1)
    except Exception:
        _logger.exception("Unexpected pipeline failure")
        sys.exit(2)


if __name__ == "__main__":
    main()

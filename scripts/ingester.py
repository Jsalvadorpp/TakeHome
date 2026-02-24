"""Ingester: fetch and store MRMS hail data for every day in a date range.

By default the range is the last 5 years (yesterday back to 5 years ago).
The end date is yesterday rather than today because today's MRMS data may
still be arriving — processing a partial day would give incomplete results.

Each day is handled by the Transformer (pipeline/transformer.py).
If a day is already in the database it is returned immediately without
hitting S3, so re-running the script is safe and cheap.

Usage:
    # Process the last 5 years (default)
    python scripts/ingester.py

    # Process a custom range
    python scripts/ingester.py --start 2024-01-01 --end 2024-12-31

    # Process a single day
    python scripts/ingester.py --start 2024-05-22 --end 2024-05-22
"""

import argparse
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

# Add the project root to sys.path so that "from pipeline.transformer import ..."
# works whether this script is run directly (python scripts/ingester.py)
# or as a module (python -m scripts.ingester).
# __file__ is .../TakeHome/scripts/ingester.py, so two dirname() calls give .../TakeHome/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.transformer import Transformer

logger = logging.getLogger(__name__)

# How many years back to go when no start date is given.
DEFAULT_LOOKBACK_YEARS = 5


# Default number of parallel workers.
# Each worker runs one day's pipeline concurrently (S3 download + decode + polygonize + DB insert).
# The heavy steps (numpy, shapely, cfgrib) are C extensions that release Python's GIL,
# so threads genuinely run in parallel for those parts.
# Raise this if your machine and DB can handle more load; lower it if you hit rate limits.
DEFAULT_WORKERS = 4


class Ingester:
    """Run the full ingest pipeline for every day in a date range.

    Days are processed in parallel using a thread pool. Days already stored
    in the database are skipped automatically — the Transformer checks the DB
    before touching S3, so re-runs are safe and cheap.

    Each worker is an independent thread with its own DB connection and S3
    client, so there is no shared state between workers.

    Example:
        ingester = Ingester()

        # Default: last 5 years, 4 parallel workers
        summary = ingester.run()
        print(summary)
        # {"total": 1825, "completed": 1800, "failed": 25}

        # Custom range with more workers
        summary = ingester.run(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            workers=8,
        )
    """

    def run(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        workers: int = DEFAULT_WORKERS,
    ) -> dict:
        """Process every day from start_date to end_date (inclusive).

        Days run in parallel. Each worker calls Transformer.run(date_str),
        which either hits the DB (fast) or runs the full S3 pipeline (slow).

        Args:
            start_date: First day to process. Default: 5 years before end_date.
            end_date:   Last day to process.  Default: yesterday.
            workers:    Number of parallel threads. Default: 4.
                        Higher values are faster but use more DB connections
                        and S3 bandwidth.

        Returns:
            A summary dict:
              - "total":     Total number of days in the range.
              - "completed": Days that finished without error.
              - "failed":    Days that raised an unexpected exception.

        Example:
            >>> ingester = Ingester()
            >>> summary = ingester.run(
            ...     start_date=date(2024, 5, 22),
            ...     end_date=date(2024, 5, 22),
            ... )
            >>> summary["total"]
            1
            >>> summary["completed"]
            1
        """
        # Default end date: yesterday, because today's data may be incomplete.
        if end_date is None:
            end_date = date.today() - timedelta(days=1)

        # Default start date: 5 years before the end date.
        if start_date is None:
            start_date = end_date - timedelta(days=DEFAULT_LOOKBACK_YEARS * 365)

        if start_date > end_date:
            raise ValueError(
                f"start_date ({start_date}) must be on or before end_date ({end_date})."
            )

        days = _date_range(start_date, end_date)
        total = len(days)

        logger.info(
            "Ingester starting: %d days from %s to %s using %d workers",
            total,
            start_date,
            end_date,
            workers,
        )

        transformer = Transformer()
        completed = 0
        failed = 0

        # Submit all days to the thread pool up front.
        # as_completed() yields each future as it finishes, so we get
        # live progress output rather than waiting for all workers to finish.
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Map each future back to its date string so we can log it on completion.
            future_to_date = {
                executor.submit(transformer.run, day.isoformat()): day.isoformat()
                for day in days
            }

            for index, future in enumerate(as_completed(future_to_date), start=1):
                date_str = future_to_date[future]
                try:
                    feature_collection = future.result()
                    feature_count = len(feature_collection["features"])
                    logger.info(
                        "[%d/%d] %s — done (%d features)",
                        index,
                        total,
                        date_str,
                        feature_count,
                    )
                    completed += 1

                except Exception as e:
                    # Log the error and keep going — one bad day should not
                    # stop the rest of the run.
                    logger.error("[%d/%d] %s — FAILED: %s", index, total, date_str, e)
                    failed += 1

        logger.info(
            "Ingester finished. %d/%d completed, %d failed.",
            completed,
            total,
            failed,
        )

        return {"total": total, "completed": completed, "failed": failed}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _date_range(start: date, end: date) -> list[date]:
    """Return a list of every date from start to end (inclusive).

    Example:
        _date_range(date(2024, 5, 22), date(2024, 5, 24))
        → [date(2024, 5, 22), date(2024, 5, 23), date(2024, 5, 24)]
    """
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _parse_date(date_str: str) -> date:
    """Parse a YYYY-MM-DD string into a date object.

    Raises:
        ValueError: If the string is not in YYYY-MM-DD format.

    Example:
        _parse_date("2024-05-22") → date(2024, 5, 22)
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"Invalid date: '{date_str}'. Expected YYYY-MM-DD, e.g. '2024-05-22'."
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(
        description=(
            "Ingest MRMS hail swath data into Postgres for every day in a date range. "
            "Defaults to the last 5 years. Days already in the database are skipped."
        )
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="First day to process (default: 5 years before --end).",
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        help="Last day to process (default: yesterday).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        metavar="N",
        help=f"Number of parallel workers (default: {DEFAULT_WORKERS}).",
    )
    args = parser.parse_args()

    start = _parse_date(args.start) if args.start else None
    end = _parse_date(args.end) if args.end else None

    ingester = Ingester()
    summary = ingester.run(start_date=start, end_date=end, workers=args.workers)

    print(
        f"\nDone — {summary['completed']}/{summary['total']} days completed, "
        f"{summary['failed']} failed."
    )

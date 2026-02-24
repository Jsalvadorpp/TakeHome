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
from datetime import date, datetime, timedelta

from pipeline.transformer import Transformer

logger = logging.getLogger(__name__)

# How many years back to go when no start date is given.
DEFAULT_LOOKBACK_YEARS = 5


class Ingester:
    """Run the full ingest pipeline for every day in a date range.

    Days already stored in the database are skipped automatically — the
    Transformer checks the DB before touching S3, so re-runs are safe.

    Example:
        ingester = Ingester()

        # Default: last 5 years
        summary = ingester.run()
        print(summary)
        # {"total": 1825, "completed": 1800, "failed": 25}

        # Custom range
        summary = ingester.run(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
    """

    def run(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        """Process every day from start_date to end_date (inclusive).

        For each day the Transformer either:
        - Returns stored data from the DB instantly (if already ingested), or
        - Fetches from S3, decodes, polygonizes, and inserts into the DB.

        Args:
            start_date: First day to process. Default: 5 years before end_date.
            end_date:   Last day to process.  Default: yesterday.

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
            "Ingester starting: %d days from %s to %s",
            total,
            start_date,
            end_date,
        )

        transformer = Transformer()
        completed = 0
        failed = 0

        for index, day in enumerate(days, start=1):
            date_str = day.isoformat()  # e.g. "2024-05-22"
            logger.info("[%d/%d] Processing %s ...", index, total, date_str)

            try:
                feature_collection = transformer.run(date_str)
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
                # Log the error and move on to the next day.
                # A single bad day should not stop the whole run.
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
    args = parser.parse_args()

    start = _parse_date(args.start) if args.start else None
    end = _parse_date(args.end) if args.end else None

    ingester = Ingester()
    summary = ingester.run(start_date=start, end_date=end)

    print(
        f"\nDone — {summary['completed']}/{summary['total']} days completed, "
        f"{summary['failed']} failed."
    )

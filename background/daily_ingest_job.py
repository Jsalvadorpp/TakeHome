"""Daily Ingest Job: run Transformer for yesterday, every 24 hours.

This background job is designed to run as a long-lived service (e.g. a Docker
container). On every cycle it processes the previous day's MRMS hail data and
stores it in Postgres. If the data is already in the database, the Transformer
skips it automatically — so restarting the service never creates duplicates.

Why yesterday and not today?
    Today's MRMS data may still be arriving from NOAA — processing a partial
    day gives incomplete swaths. Yesterday's data is always complete.

Usage:
    # Run continuously — blocks until stopped (designed for Docker / production)
    python -m background.daily_ingest_job

    # Run once and exit — useful for testing or a manual one-off trigger
    python -m background.daily_ingest_job --once
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

# Add the project root to sys.path so that imports like
# "from pipeline.transformer import Transformer" work when this script
# is run directly (python -m background.daily_ingest_job).
# __file__ is .../TakeHome/background/daily_ingest_job.py, so two
# dirname() calls give .../TakeHome/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.transformer import Transformer

logger = logging.getLogger(__name__)

# How long to sleep between runs (24 hours expressed in seconds).
INTERVAL_SECONDS = 24 * 60 * 60


def _seconds_until_noon_utc() -> float:
    """Return how many seconds remain until 12:00 UTC today.

    Returns 0 if it is already past noon UTC — no waiting needed.

    The noon-to-noon window for "yesterday" closes at 12:00 UTC today, so the
    daily job should not run before that point or it risks processing an
    incomplete window.

    Example:
        At 10:00 UTC → returns 7200.0  (2 hours to wait)
        At 13:00 UTC → returns 0.0     (already past noon, run immediately)
    """
    now = datetime.now(timezone.utc)
    noon_today = now.replace(hour=12, minute=0, second=0, microsecond=0)
    if now >= noon_today:
        return 0.0
    return (noon_today - now).total_seconds()


class DailyIngestJob:
    """Process yesterday's MRMS hail data on a 24-hour repeating schedule.

    The job runs immediately on startup, then sleeps 24 hours and repeats.
    This means there is never a full 24-hour wait before the first run.

    If a day's data is already in the database, the Transformer skips it —
    so restarting this service is always safe.

    Example:
        job = DailyIngestJob()

        # Run once (useful for testing or a manual trigger)
        result = job.run_once()
        print(result)
        # {"date": "2024-05-22", "feature_count": 47}

        # Run forever — this blocks the process
        job.start()
    """

    def run_once(self) -> dict:
        """Process yesterday's MRMS hail data.

        "Yesterday" is always used rather than today because today's MRMS
        data may still be arriving from NOAA. Processing a partial day
        would give an incomplete swath.

        Returns:
            A dict with:
              - "date":          The date that was processed (YYYY-MM-DD string).
              - "feature_count": Number of hail polygons stored.

        Example:
            >>> job = DailyIngestJob()
            >>> result = job.run_once()
            >>> result["feature_count"]
            47
        """
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        logger.info("Daily ingest starting for %s", yesterday)

        transformer = Transformer()
        feature_collection = transformer.run(yesterday)
        feature_count = len(feature_collection["features"])

        logger.info(
            "Daily ingest complete for %s — %d features stored",
            yesterday,
            feature_count,
        )

        return {"date": yesterday, "feature_count": feature_count}

    def start(self) -> None:
        """Run forever: process yesterday, sleep 24 hours, repeat.

        This method blocks the calling process indefinitely. It is designed
        to run as a long-lived background service (e.g. a Docker container).

        The job runs immediately on startup — there is no 24-hour wait
        before the first execution. After each run it sleeps 24 hours
        before running again.

        If a single run fails (e.g. S3 is temporarily unavailable), the
        error is logged and the job sleeps and tries again the next day.
        One failure never stops the job permanently.

        Example:
            job = DailyIngestJob()
            job.start()  # blocks forever — Ctrl+C or SIGTERM to stop
        """
        logger.info("Daily ingest job started. Runs at or after 12:00 UTC each day.")

        while True:
            # The noon-to-noon window for "yesterday" closes at 12:00 UTC today.
            # If the job starts before noon UTC, wait until noon before running.
            wait_seconds = _seconds_until_noon_utc()
            if wait_seconds > 0:
                logger.info(
                    "Waiting %.0f minutes until 12:00 UTC before running...",
                    wait_seconds / 60,
                )
                time.sleep(wait_seconds)

            try:
                self.run_once()
            except Exception as e:
                # Log the error but keep the loop alive.
                # A single bad day should not stop tomorrow's run.
                logger.error("Daily ingest run failed: %s", e)

            logger.info("Next run in 24 hours. Sleeping...")
            time.sleep(INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(
        description=(
            "Daily MRMS hail ingest job. "
            "Processes yesterday's data and stores it in Postgres. "
            "Runs every 24 hours by default."
        )
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once for yesterday and exit (instead of looping every 24 hours).",
    )
    args = parser.parse_args()

    job = DailyIngestJob()

    if args.once:
        result = job.run_once()
        print(f"\nDone — {result['feature_count']} features stored for {result['date']}.")
    else:
        job.start()

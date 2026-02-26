"""Transformer: fetch, process, and store MRMS hail data for a single calendar day.

This module is the batch/ETL counterpart to the API's _build_swaths function.
It takes a date, pulls the MRMS GRIB2 file for that full day from S3,
polygonizes hail swaths at all standard thresholds, and stores them in Postgres.

Unlike the API, this module does NOT take start_time/end_time/thresholds/bbox/simplify
as parameters. It always processes the entire day at all thresholds so the database
ends up with complete data that the API can later filter however it needs.

Usage:
    from pipeline.transformer import Transformer

    t = Transformer()
    feature_collection = t.run("2024-05-22")
    print(f"Stored {len(feature_collection['features'])} polygons for 2024-05-22")

Or as a CLI script:
    python -m pipeline.transformer 2024-05-22
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from db.client import get_connection
from db.repository import create_tables, get_swaths, insert_swaths, swaths_exist
from ingest.fetcher import PRODUCT_PREFIX, fetch_file, list_files
from processing.decoder import decode_grib2
from processing.polygonize import THRESHOLDS_INCHES, grid_to_swaths

logger = logging.getLogger(__name__)

# Standard hail thresholds used across the system (in inches).
# These match THRESHOLDS_INCHES in processing/polygonize.py.
# 0.50" is the minimum; 2.75" is well above baseball-sized hail.
DEFAULT_THRESHOLDS = THRESHOLDS_INCHES


class Transformer:
    """Fetch, process, and store MRMS hail swaths for a single calendar day.

    One Transformer instance can be reused to process multiple dates.

    Example:
        transformer = Transformer()

        # Process a single day and get back the GeoJSON
        fc = transformer.run("2024-05-22")
        print(fc["type"])             # "FeatureCollection"
        print(len(fc["features"]))    # e.g. 47 polygons across all thresholds

        # If that date is already in the DB, it returns from DB immediately
        fc2 = transformer.run("2024-05-22")  # fast — no S3 call
    """

    def run(self, date_str: str) -> dict:
        """Fetch and store hail swaths for the given calendar date.

        Steps:
          1. Parse and validate the date string.
          2. Check if the date already exists in the database.
             - If yes, return the stored data immediately (no S3 call).
          3. List MRMS files on S3 for that full day.
          4. Download the last file (MESH_Max_1440min is a 24-hour rolling max,
             so the last file already captures the full day's maximum hail).
          5. Decode the GRIB2 file into a hail-size grid (in inches).
          6. Polygonize at all standard thresholds across the full CONUS grid.
             No bounding box clipping is applied — full data is stored so any
             future API request with a different bbox can still use the DB row.
          7. Insert into the database (one row per date).
          8. Delete the local GRIB2 cache file to save disk space.
          9. Return the GeoJSON FeatureCollection.

        Args:
            date_str: Calendar date in YYYY-MM-DD format.
                      Example: "2024-05-22"

        Returns:
            A GeoJSON FeatureCollection dict containing hail swath polygons.
            Each feature has properties: threshold, product, start_time,
            end_time, source_files, created_at.

            Returns an empty FeatureCollection if no MRMS data is available
            for the requested date.

        Raises:
            ValueError: If date_str is not in YYYY-MM-DD format.
            RuntimeError: If the database connection cannot be established.

        Example:
            >>> t = Transformer()
            >>> fc = t.run("2024-05-22")
            >>> fc["type"]
            'FeatureCollection'
            >>> fc["features"][0]["properties"]["threshold"]
            2.0
        """
        # Step 1: Validate the date string. Raises ValueError if format is wrong.
        valid_date = _parse_date(date_str)

        # Build UTC timestamps for the 24-hour window starting at noon on the given date.
        # Example for "2024-05-22":
        #   start = 2024-05-22 12:00:00 UTC
        #   end   = 2024-05-23 12:00:00 UTC  (exactly 24 hours later)
        # Using noon-to-noon instead of midnight-to-midnight captures storm data that
        # spans across a calendar-day boundary (storms that start in the afternoon and
        # continue into the next morning are kept together in one window).
        start_of_day = datetime(valid_date.year, valid_date.month, valid_date.day, 12, 0, 0, tzinfo=timezone.utc)
        end_of_day = start_of_day + timedelta(hours=24)

        start_time_iso = start_of_day.isoformat()
        end_time_iso = end_of_day.isoformat()

        conn = get_connection()
        try:
            # Make sure the hail_swaths table exists before anything else.
            create_tables(conn)

            # Step 2: DB hit check — if data for this date is already stored,
            # return it immediately without hitting S3.
            if swaths_exist(conn, date_str):
                logger.info("DB hit for %s — returning stored data", date_str)
                return get_swaths(conn, date_str)

            logger.info("DB miss for %s — starting S3 pipeline", date_str)

            # Step 3: List MRMS files on S3 for the full calendar day.
            t0 = time.time()
            keys = list_files(PRODUCT_PREFIX, start_of_day, end_of_day)
            logger.info("Listed %d S3 files in %.1fs", len(keys), time.time() - t0)

            if len(keys) == 0:
                logger.warning("No MRMS files found on S3 for %s", date_str)
                return _empty_feature_collection()

            # Step 4: Use only the last file.
            # MESH_Max_1440min is a 24-hour rolling maximum — the last file in
            # the day already contains the maximum hail over the full window.
            if len(keys) > 1:
                logger.info(
                    "Found %d files — using last one (1440min rolling max covers full day)",
                    len(keys),
                )
            last_key = keys[-1]

            # Download and decompress the file into the local cache.
            t0 = time.time()
            try:
                local_path = fetch_file(last_key)
            except Exception as e:
                logger.warning("Failed to download %s: %s", last_key, e)
                return _empty_feature_collection()
            logger.info("Downloaded %s in %.1fs", local_path.name, time.time() - t0)

            # Step 5: Decode GRIB2 → numpy array (hail sizes in inches), affine transform.
            t0 = time.time()
            try:
                data, transform, _ = decode_grib2(local_path)
            except Exception as e:
                logger.warning("Failed to decode %s: %s", local_path.name, e)
                return _empty_feature_collection()
            logger.info("Decoded GRIB2 in %.1fs, grid shape %s", time.time() - t0, data.shape)

            # Step 6: Polygonize at all standard thresholds over the full CONUS grid.
            # No bbox clipping so the stored data can serve any future API query.
            t0 = time.time()
            fc = grid_to_swaths(
                data=data,
                transform=transform,
                thresholds=DEFAULT_THRESHOLDS,
                product="MESH_Max_1440min",
                start_time=start_time_iso,
                end_time=end_time_iso,
                source_files=[local_path.name],
                bbox=None,
            )
            logger.info(
                "Polygonized %d features in %.1fs",
                len(fc["features"]),
                time.time() - t0,
            )

            # Step 7: Insert into the database. One row per date.
            # insert_swaths uses ON CONFLICT DO NOTHING so it's safe to call twice.
            inserted = insert_swaths(conn, fc, date_str)
            if inserted:
                logger.info("Inserted swath data for %s into DB", date_str)
            else:
                logger.info("Data for %s already existed in DB — skipped insert", date_str)

            # Step 8: Delete the GRIB2 file — data is safely stored in Postgres.
            if local_path.exists():
                local_path.unlink()
                logger.info("Deleted cached file: %s", local_path.name)

            # Step 9: Return from the DB so the caller always gets the persisted version.
            return get_swaths(conn, date_str)

        finally:
            conn.close()


def _parse_date(date_str: str):
    """Parse a YYYY-MM-DD string into a datetime.date object.

    Raises ValueError if the string is not in the expected format.

    Example:
        _parse_date("2024-05-22") → date(2024, 5, 22)
        _parse_date("bad input")  → raises ValueError
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date: '{date_str}'. Expected YYYY-MM-DD format, e.g. '2024-05-22'.")


def _empty_feature_collection() -> dict:
    """Return a valid but empty GeoJSON FeatureCollection.

    Used when no MRMS data is available for the requested date.

    Example:
        _empty_feature_collection()
        → {"type": "FeatureCollection", "features": []}
    """
    return {"type": "FeatureCollection", "features": []}


# Allow running as a CLI script: python -m pipeline.transformer 2024-05-22
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if len(sys.argv) != 2:
        print("Usage: python -m pipeline.transformer YYYY-MM-DD")
        print("Example: python -m pipeline.transformer 2024-05-22")
        sys.exit(1)

    date_arg = sys.argv[1]
    transformer = Transformer()
    result = transformer.run(date_arg)
    print(f"Done. {len(result['features'])} polygons stored for {date_arg}.")

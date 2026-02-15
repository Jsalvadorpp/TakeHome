"""Fetch MRMS GRIB2 files from the public NOAA S3 bucket."""

import gzip
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore import UNSIGNED
from botocore.config import Config

logger = logging.getLogger(__name__)

BUCKET = "noaa-mrms-pds"
PRODUCT_PREFIX = "CONUS/MESH_Max_60min_00.50"
FILENAME_PREFIX = "MRMS_MESH_Max_60min_00.50"
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"


def get_s3_client():
    """Create an S3 client with unsigned (public) access."""
    return boto3.client("s3", config=Config(signature_version=UNSIGNED))


def _parse_timestamp_from_filename(filename: str) -> datetime | None:
    """Extract the timestamp embedded in an MRMS filename.

    Example:
        Input:  "MRMS_MESH_Max_60min_00.50_20240522-200000.grib2.gz"
        Output: datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)

    Returns None if parsing fails.
    """
    try:
        # Strip directory path if present
        name = filename.split("/")[-1]

        # Remove the file extensions (.grib2.gz or .grib2)
        name = name.replace(".grib2.gz", "").replace(".grib2", "")

        # The timestamp is the last part after the final underscore
        # MRMS_MESH_Max_60min_00.50_20240522-200000
        timestamp_str = name.split("_")[-1]

        dt = datetime.strptime(timestamp_str, TIMESTAMP_FORMAT)
        return dt.replace(tzinfo=timezone.utc)
    except (ValueError, IndexError) as e:
        logger.warning("Could not parse timestamp from filename: %s (%s)", filename, e)
        return None


def _decompress_gz(gz_path: Path) -> Path:
    """Decompress a .gz file and return the path to the decompressed file."""
    decompressed_path = gz_path.with_suffix("")  # removes .gz

    with gzip.open(gz_path, "rb") as f_in:
        with open(decompressed_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    # Remove the .gz file to save space
    gz_path.unlink()

    return decompressed_path


def list_files(product: str, start: datetime, end: datetime) -> list[str]:
    """List S3 keys for an MRMS product between start and end times.

    Parses timestamps from the S3 key names to filter by time range.
    Returns an empty list if no files are found.
    """
    # Make sure start/end are timezone-aware for comparison
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    s3 = get_s3_client()
    matching_keys = []

    # MRMS files are organized by date: PRODUCT_PREFIX/YYYYMMDD/
    # We need to check each date folder between start and end
    current_date = start.date()
    end_date = end.date()

    while current_date <= end_date:
        date_str = current_date.strftime("%Y%m%d")
        prefix = f"{product}/{date_str}/"

        try:
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    timestamp = _parse_timestamp_from_filename(key)
                    if timestamp is None:
                        continue
                    if start <= timestamp <= end:
                        matching_keys.append(key)
        except Exception as e:
            logger.warning("Error listing S3 prefix %s: %s", prefix, e)

        # Move to next day
        current_date = current_date + timedelta(days=1)

    matching_keys.sort()
    return matching_keys


def fetch_file(s3_key: str, cache_dir: Path = Path("./cache")) -> Path:
    """Download a file from S3 to the local cache. Returns the local path.

    Skips the download if the file already exists in cache.
    Decompresses .gz files after downloading.
    """
    # Get just the filename from the S3 key
    filename = s3_key.split("/")[-1]

    # The final file will be decompressed (.grib2, not .grib2.gz)
    final_filename = filename.replace(".gz", "")
    final_path = cache_dir / final_filename

    # If the decompressed file already exists, skip download
    if final_path.exists():
        logger.info("Cache hit: %s", final_filename)
        return final_path

    # Make sure the cache directory exists
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Download the file
    gz_path = cache_dir / filename
    s3 = get_s3_client()

    try:
        logger.info("Downloading: %s", s3_key)
        s3.download_file(BUCKET, s3_key, str(gz_path))
    except Exception as e:
        logger.warning("Failed to download %s: %s", s3_key, e)
        # Clean up partial download
        if gz_path.exists():
            gz_path.unlink()
        raise

    # Decompress if it's a .gz file
    if filename.endswith(".gz"):
        final_path = _decompress_gz(gz_path)

    return final_path

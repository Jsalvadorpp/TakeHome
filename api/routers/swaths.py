"""Hail swath polygon endpoints.

This module contains everything related to hail swath generation:
- API endpoint definitions (GET /swaths, GET /swaths/file)
- Business logic for building swaths (_build_swaths)

The first request for a given date fetches from S3, processes the data,
and stores all polygons in Postgres. Every subsequent request for that
date is served directly from the database — no S3 call needed.
"""

import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.common.parsers import parse_time, parse_thresholds, parse_bbox
from db.client import get_connection
from db.repository import swaths_exist, insert_swaths, get_swaths as db_get_swaths
from ingest.fetcher import list_files, fetch_file, PRODUCT_PREFIX
from processing.decoder import decode_grib2
from processing.polygonize import grid_to_swaths, composite_max, THRESHOLDS_INCHES

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_swaths(start_time: str, end_time: str, thresholds: str | None, bbox: str | None, simplify: float | None) -> dict:
    """Return hail swath polygons for the requested parameters.

    Checks the database first. If the data for that date is already stored,
    it returns immediately from the DB. If not, it runs the full S3 pipeline
    (fetch → decode → polygonize), stores all results in the DB, then returns.

    Data is always stored for ALL thresholds and without a bbox so that any
    future request for the same date (with different thresholds or bbox) can
    still be served from the DB without hitting S3 again.

    Args:
        start_time: ISO8601 start time (e.g., "2024-05-22T20:00:00Z")
        end_time: ISO8601 end time
        thresholds: Comma-separated thresholds (e.g., "0.75,1.0,1.5") or None for defaults
        bbox: Bounding box "minLon,minLat,maxLon,maxLat" or None
        simplify: Simplification tolerance in degrees or None for default (0.005)

    Returns:
        GeoJSON FeatureCollection dict with hail polygons

    Raises:
        HTTPException(400): If parameters are invalid
        HTTPException(404): If no files found or all downloads/decodes failed
        HTTPException(500): If all files failed to decode
    """
    # Parse and validate all parameters up front (fail fast before any I/O)
    try:
        start_dt = parse_time(start_time)
        end_dt = parse_time(end_time)
        threshold_list = parse_thresholds(thresholds, default=THRESHOLDS_INCHES)
        bbox_tuple = parse_bbox(bbox)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    simplify_tolerance = simplify if simplify is not None else 0.005

    # The date (e.g. "2024-05-22") is the key used to look up stored data.
    # Since we use the 1440min product (24-hour max), one date = one file = one full swath.
    valid_date = start_dt.date().isoformat()

    conn = get_connection()
    try:
        # --- DB hit: data already stored for this date ---
        if swaths_exist(conn, valid_date):
            logger.info("DB hit for %s — serving from database", valid_date)
            return db_get_swaths(conn, valid_date, threshold_list, bbox_tuple)

        # --- DB miss: fetch from S3, process, then store ---
        logger.info("DB miss for %s — fetching from S3", valid_date)

        # Step 1: List files
        t0 = time.time()
        keys = list_files(PRODUCT_PREFIX, start_dt, end_dt)
        logger.info("Listed %d files in %.1fs", len(keys), time.time() - t0)

        if len(keys) == 0:
            raise HTTPException(status_code=404, detail="No MRMS files found for this time window.")

        # MESH_Max_1440min is a 24-hour rolling max: the last file in the window
        # already contains the maximum hail over the entire requested period.
        # We only ever need that one file.
        if len(keys) > 1:
            logger.info("Using last of %d files (1440min rolling max covers full window)", len(keys))
            keys = [keys[-1]]

        # Step 2: Fetch files
        t0 = time.time()
        local_paths = []
        for key in keys:
            try:
                path = fetch_file(key)
                local_paths.append(path)
            except Exception as e:
                logger.warning("Skipping %s: %s", key, e)
        logger.info("Fetched %d files in %.1fs", len(local_paths), time.time() - t0)

        if len(local_paths) == 0:
            raise HTTPException(status_code=404, detail="All MRMS files failed to download.")

        # Step 3: Decode files
        t0 = time.time()
        arrays = []
        transform = None
        for path in local_paths:
            try:
                data, file_transform, _ = decode_grib2(path)
                arrays.append(data)
                if transform is None:
                    transform = file_transform
            except Exception as e:
                logger.warning("Skipping %s: %s", path.name, e)
        logger.info("Decoded %d files in %.1fs", len(arrays), time.time() - t0)

        if len(arrays) == 0:
            raise HTTPException(status_code=500, detail="All MRMS files failed to decode.")

        # Step 4: Composite if multiple files
        if len(arrays) > 1:
            data = composite_max(arrays)
        else:
            data = arrays[0]

        # Step 5: Polygonize ALL thresholds with NO bbox clipping.
        # We store the full CONUS data so that any future request for this date
        # (with different thresholds or a different bbox) can be served from DB.
        t0 = time.time()
        source_filenames = [p.name for p in local_paths]
        fc = grid_to_swaths(
            data=data,
            transform=transform,
            thresholds=THRESHOLDS_INCHES,
            product="MESH_Max_1440min",
            start_time=start_time,
            end_time=end_time,
            source_files=source_filenames,
            bbox=None,
            simplify_tolerance=simplify_tolerance,
        )
        logger.info("Polygonized in %.1fs, %d features", time.time() - t0, len(fc["features"]))

        # Step 6: Store in DB
        insert_swaths(conn, fc, valid_date)

        # Step 7: Delete the downloaded GRIB2 files — data is now in the DB
        for path in local_paths:
            if path.exists():
                path.unlink()
                logger.info("Removed cached file: %s", path.name)

        # Step 8: Return from DB with the user's threshold and bbox filters applied
        return db_get_swaths(conn, valid_date, threshold_list, bbox_tuple)

    finally:
        conn.close()


@router.get("/swaths")
def get_swaths(
    start_time: str,
    end_time: str,
    thresholds: str | None = None,
    bbox: str | None = None,
    simplify: float | None = None,
):
    """Return hail swath polygons as a GeoJSON FeatureCollection.

    Args:
        start_time: ISO8601 start time (e.g., "2024-05-22T20:00:00Z")
        end_time: ISO8601 end time
        thresholds: Comma-separated thresholds in inches (e.g., "0.75,1.0,1.5")
        bbox: Bounding box "minLon,minLat,maxLon,maxLat" (optional)
        simplify: Simplification tolerance in degrees (optional, default 0.005)

    Returns:
        GeoJSON FeatureCollection with hail polygons

    Example:
        GET /swaths?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z
    """
    return _build_swaths(start_time, end_time, thresholds, bbox, simplify)


@router.get("/swaths/file")
def get_swaths_file(
    start_time: str,
    end_time: str,
    thresholds: str | None = None,
    bbox: str | None = None,
    simplify: float | None = None,
):
    """Return hail swath polygons as a downloadable .geojson file.

    Args:
        start_time: ISO8601 start time (e.g., "2024-05-22T20:00:00Z")
        end_time: ISO8601 end time
        thresholds: Comma-separated thresholds in inches (e.g., "0.75,1.0,1.5")
        bbox: Bounding box "minLon,minLat,maxLon,maxLat" (optional)
        simplify: Simplification tolerance in degrees (optional, default 0.005)

    Returns:
        Downloadable .geojson file with hail polygons

    Example:
        GET /swaths/file?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z
    """
    fc = _build_swaths(start_time, end_time, thresholds, bbox, simplify)
    content = json.dumps(fc, indent=2)
    return Response(
        content=content,
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=swaths.geojson"},
    )

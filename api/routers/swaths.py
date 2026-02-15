"""Hail swath polygon endpoints.

This module contains everything related to hail swath generation:
- API endpoint definitions (GET /swaths, GET /swaths/file)
- Business logic for building swaths (_build_swaths)
- Caching infrastructure
"""

import json
import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.common.parsers import parse_time, parse_thresholds, parse_bbox
from ingest.fetcher import list_files, fetch_file, PRODUCT_PREFIX
from processing.decoder import decode_grib2
from processing.polygonize import grid_to_swaths, composite_max, THRESHOLDS_INCHES

logger = logging.getLogger(__name__)
router = APIRouter()

# Simple in-memory cache: cache_key -> FeatureCollection
_cache: dict[str, dict] = {}


def _build_cache_key(start: str, end: str, thresholds: str | None, bbox: str | None, simplify: float | None) -> str:
    """Build a string key for caching results.

    Example:
        Input:  start="2024-05-22T20:00:00Z", end="2024-05-22T22:00:00Z",
                thresholds="0.75,1.0", bbox=None, simplify=0.005
        Output: "2024-05-22T20:00:00Z|2024-05-22T22:00:00Z|0.75,1.0|None|0.005"
    """
    return f"{start}|{end}|{thresholds}|{bbox}|{simplify}"


def _build_swaths(start_time: str, end_time: str, thresholds: str | None, bbox: str | None, simplify: float | None) -> dict:
    """Run the full pipeline: list files, fetch, decode, composite, polygonize.

    This is the heavyweight orchestration function that:
    1. Parses and validates parameters
    2. Checks cache for existing results
    3. Lists available MRMS files from S3
    4. Fetches and decodes GRIB2 files
    5. Composites multiple grids into one
    6. Polygonizes into GeoJSON features
    7. Caches the result

    Args:
        start_time: ISO8601 start time (e.g., "2024-05-22T20:00:00Z")
        end_time: ISO8601 end time
        thresholds: Comma-separated thresholds (e.g., "0.75,1.0,1.5") or None for defaults
        bbox: Bounding box "minLon,minLat,maxLon,maxLat" or None
        simplify: Simplification tolerance in degrees or None for default (0.005)

    Returns:
        GeoJSON FeatureCollection dict with all polygons

    Raises:
        HTTPException(400): If parameters are invalid
        HTTPException(404): If no files found or all downloads/decodes failed
        HTTPException(500): If all files failed to decode
    """
    cache_key = _build_cache_key(start_time, end_time, thresholds, bbox, simplify)
    if cache_key in _cache:
        logger.info("Cache hit for %s", cache_key)
        return _cache[cache_key]

    # Parse and validate parameters (convert ValueError to HTTPException)
    try:
        start_dt = parse_time(start_time)
        end_dt = parse_time(end_time)
        threshold_list = parse_thresholds(thresholds, default=THRESHOLDS_INCHES)
        bbox_tuple = parse_bbox(bbox)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    simplify_tolerance = simplify if simplify is not None else 0.005

    # Step 1: List files
    t0 = time.time()
    keys = list_files(PRODUCT_PREFIX, start_dt, end_dt)
    logger.info("Listed %d files in %.1fs", len(keys), time.time() - t0)

    if len(keys) == 0:
        raise HTTPException(status_code=404, detail="No MRMS files found for this time window.")

    # Sample files to avoid processing redundant data.
    # MESH_Max_60min is already a 60-minute rolling max, so we only need
    # one file per ~60 minutes for full coverage of any time window.
    # Files are 2 minutes apart, so every 30th file = every 60 minutes.
    SAMPLE_STEP = 30
    if len(keys) > SAMPLE_STEP:
        sampled = keys[::SAMPLE_STEP]
        if keys[-1] not in sampled:
            sampled.append(keys[-1])
        logger.info("Sampled %d files down to %d", len(keys), len(sampled))
        keys = sampled

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
            data, file_transform, meta = decode_grib2(path)
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

    # Step 5: Polygonize
    t0 = time.time()
    source_filenames = [p.name for p in local_paths]
    fc = grid_to_swaths(
        data=data,
        transform=transform,
        thresholds=threshold_list,
        product="MESH_Max_60min",
        start_time=start_time,
        end_time=end_time,
        source_files=source_filenames,
        bbox=bbox_tuple,
        simplify_tolerance=simplify_tolerance,
    )
    logger.info("Polygonized in %.1fs, %d features", time.time() - t0, len(fc["features"]))

    _cache[cache_key] = fc
    return fc


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

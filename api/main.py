"""FastAPI application for serving hail swath polygons."""

import json
import logging
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from ingest.fetcher import list_files, fetch_file, PRODUCT_PREFIX
from processing.decoder import decode_grib2
from processing.polygonize import grid_to_swaths, composite_max, THRESHOLDS_INCHES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="MRMS Hail Swaths API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory cache: cache_key -> FeatureCollection
_cache: dict[str, dict] = {}


def _parse_time(value: str) -> datetime:
    """Parse an ISO8601 time string into a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid time format: {value}")


def _parse_thresholds(value: str | None) -> list[float]:
    """Parse comma-separated thresholds string into a list of floats."""
    if value is None:
        return THRESHOLDS_INCHES

    try:
        return [float(t.strip()) for t in value.split(",")]
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid thresholds: {value}")


def _parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse bbox string (minLon,minLat,maxLon,maxLat) into a tuple."""
    if value is None:
        return None

    try:
        parts = [float(p.strip()) for p in value.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must have 4 values")
        return (parts[0], parts[1], parts[2], parts[3])
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid bbox: {value}")


def _build_cache_key(start: str, end: str, thresholds: str | None, bbox: str | None, simplify: float | None) -> str:
    """Build a string key for caching results."""
    return f"{start}|{end}|{thresholds}|{bbox}|{simplify}"


def _build_swaths(start_time: str, end_time: str, thresholds: str | None, bbox: str | None, simplify: float | None) -> dict:
    """Run the full pipeline: list files, fetch, decode, composite, polygonize."""
    cache_key = _build_cache_key(start_time, end_time, thresholds, bbox, simplify)
    if cache_key in _cache:
        logger.info("Cache hit for %s", cache_key)
        return _cache[cache_key]

    start_dt = _parse_time(start_time)
    end_dt = _parse_time(end_time)
    threshold_list = _parse_thresholds(thresholds)
    bbox_tuple = _parse_bbox(bbox)
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


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"ok": True}


@app.get("/swaths")
def get_swaths(
    start_time: str,
    end_time: str,
    thresholds: str | None = None,
    bbox: str | None = None,
    simplify: float | None = None,
):
    """Return hail swath polygons as a GeoJSON FeatureCollection."""
    return _build_swaths(start_time, end_time, thresholds, bbox, simplify)


@app.get("/swaths/file")
def get_swaths_file(
    start_time: str,
    end_time: str,
    thresholds: str | None = None,
    bbox: str | None = None,
    simplify: float | None = None,
):
    """Return hail swath polygons as a downloadable .geojson file."""
    fc = _build_swaths(start_time, end_time, thresholds, bbox, simplify)
    content = json.dumps(fc, indent=2)
    return Response(
        content=content,
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=swaths.geojson"},
    )

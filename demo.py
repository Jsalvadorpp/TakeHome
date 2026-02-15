"""CLI script to generate hail swath polygons and write a GeoJSON file.

Usage:
    python demo.py --start 2024-05-22T20:00:00Z --end 2024-05-22T22:00:00Z --output swaths.geojson
"""

import argparse
import json
import logging
import sys
import time

from api.common.parsers import parse_time, parse_thresholds, parse_bbox
from ingest.fetcher import list_files, fetch_file, PRODUCT_PREFIX
from processing.decoder import decode_grib2
from processing.polygonize import grid_to_swaths, composite_max, THRESHOLDS_INCHES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate MRMS hail swath polygons.")
    parser.add_argument("--start", required=True, help="Start time in ISO8601 format")
    parser.add_argument("--end", required=True, help="End time in ISO8601 format")
    parser.add_argument("--output", default="swaths.geojson", help="Output file path")
    parser.add_argument(
        "--thresholds",
        default="0.75,1.00,1.50,2.00",
        help="Comma-separated thresholds in inches",
    )
    parser.add_argument(
        "--bbox",
        default=None,
        help="Bounding box: minLon,minLat,maxLon,maxLat",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Parse arguments
    try:
        start_dt = parse_time(args.start)
        end_dt = parse_time(args.end)
        thresholds = parse_thresholds(args.thresholds)
        bbox = parse_bbox(args.bbox)
    except ValueError as e:
        logger.error("Invalid argument: %s", e)
        sys.exit(1)

    # Step 1: List files
    t0 = time.time()
    logger.info("Listing files from %s to %s...", args.start, args.end)
    keys = list_files(PRODUCT_PREFIX, start_dt, end_dt)
    logger.info("Found %d files in %.1fs", len(keys), time.time() - t0)

    if len(keys) == 0:
        logger.warning("No files found. Writing empty FeatureCollection.")
        empty = {"type": "FeatureCollection", "features": []}
        with open(args.output, "w") as f:
            json.dump(empty, f, indent=2)
        print(f"Wrote 0 features to {args.output}")
        return

    # Sample files (MESH_Max_60min covers 60-min windows, so one per hour is enough)
    SAMPLE_STEP = 30
    if len(keys) > SAMPLE_STEP:
        sampled = keys[::SAMPLE_STEP]
        if keys[-1] not in sampled:
            sampled.append(keys[-1])
        logger.info("Sampled %d files down to %d", len(keys), len(sampled))
        keys = sampled

    # Step 2: Fetch files
    t0 = time.time()
    logger.info("Fetching %d files...", len(keys))
    local_paths = []
    for key in keys:
        try:
            path = fetch_file(key)
            local_paths.append(path)
        except Exception as e:
            logger.warning("Skipping %s: %s", key, e)
    logger.info("Fetched %d files in %.1fs", len(local_paths), time.time() - t0)

    if len(local_paths) == 0:
        logger.error("All files failed to download.")
        sys.exit(1)

    # Step 3: Decode files
    t0 = time.time()
    logger.info("Decoding %d files...", len(local_paths))
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
        logger.error("All files failed to decode.")
        sys.exit(1)

    # Step 4: Composite
    if len(arrays) > 1:
        data = composite_max(arrays)
    else:
        data = arrays[0]

    # Step 5: Polygonize
    t0 = time.time()
    logger.info("Generating swath polygons...")
    source_filenames = [p.name for p in local_paths]
    fc = grid_to_swaths(
        data=data,
        transform=transform,
        thresholds=thresholds,
        product="MESH_Max_60min",
        start_time=args.start,
        end_time=args.end,
        source_files=source_filenames,
        bbox=bbox,
    )
    logger.info("Generated %d features in %.1fs", len(fc["features"]), time.time() - t0)

    # Step 6: Write output
    with open(args.output, "w") as f:
        json.dump(fc, f, indent=2)

    print(f"\nWrote {len(fc['features'])} features to {args.output}")
    print(f"Thresholds: {thresholds}")
    if bbox:
        print(f"Bbox: {bbox}")


if __name__ == "__main__":
    main()

"""CLI script to generate hail swath polygons and write a GeoJSON file.

Usage:
    python demo.py --start 2024-05-21T18:00:00Z --end 2024-05-21T23:00:00Z --output swaths.geojson
"""

import argparse
import json
import logging
import sys
from datetime import datetime

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

    # TODO: Implement in Step 6
    # 1. Parse arguments
    # 2. Call ingest.list_files() for the time range
    # 3. Call ingest.fetch_file() for each file
    # 4. Call processing.decode_grib2() on each file
    # 5. If multiple files, call processing.composite_max()
    # 6. Call processing.grid_to_swaths() with thresholds
    # 7. Write the FeatureCollection to the output file

    logger.info("demo.py is not yet implemented. Run after completing Steps 1-3.")
    sys.exit(1)


if __name__ == "__main__":
    main()

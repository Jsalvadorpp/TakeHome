"""Read and write hail swaths to/from Postgres.

These functions are used by:
- api/  → swaths_exist() + get_swaths() to serve the web viewer
          insert_swaths() to store processed data after an S3 fetch

Storage design: one row per date.
All polygons for all thresholds are stored together in a single JSONB array.
Each polygon feature carries its own `threshold` property so we can still
filter by threshold when reading.

No PostGIS required. Geometry is stored as plain JSONB.
Bounding box filtering is done in Python using Shapely.
"""

import json
import logging

from shapely.geometry import box, mapping, shape
from shapely.validation import make_valid

logger = logging.getLogger(__name__)


def create_tables(conn) -> None:
    """Create the hail_swaths table and index if they don't already exist.

    Safe to call every time the app starts — uses IF NOT EXISTS so it only
    creates the table on the first run and does nothing on subsequent runs.

    Schema: one row per date. All threshold polygons stored together.

    Args:
        conn: An open psycopg2 connection.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hail_swaths (
                id           SERIAL PRIMARY KEY,
                features     JSONB        NOT NULL,  -- all polygons for all thresholds (flat JSON array)
                product      TEXT         NOT NULL,  -- MRMS product name
                valid_date   DATE         NOT NULL,  -- calendar date this swath covers
                start_time   TIMESTAMPTZ,
                end_time     TIMESTAMPTZ,
                source_files TEXT[],
                created_at   TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE (valid_date)                  -- one row per date, no duplicates
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS hail_swaths_date_idx
                ON hail_swaths (valid_date);
        """)
    conn.commit()
    logger.info("Database tables ready")


def swaths_exist(conn, valid_date: str) -> bool:
    """Return True if the DB already has swath data for this date.

    Used by the API to decide whether to skip the S3 pipeline and serve
    directly from the database instead.

    Args:
        conn: An open psycopg2 connection.
        valid_date: Date string, e.g. "2024-05-22".
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM hail_swaths WHERE valid_date = %s LIMIT 1",
            (valid_date,),
        )
        return cur.fetchone() is not None


def insert_swaths(conn, feature_collection: dict, valid_date: str) -> int:
    """Insert one row for the date, storing all threshold polygons together.

    All polygons from all thresholds are stored as a single flat JSON array.
    Each polygon feature keeps its `threshold` property so it can be filtered later.

    Uses ON CONFLICT DO NOTHING so running it twice for the same date is safe.

    Args:
        conn: An open psycopg2 connection.
        feature_collection: GeoJSON FeatureCollection dict (from grid_to_swaths).
        valid_date: The calendar date these swaths cover, e.g. "2024-05-22".

    Returns:
        1 if a row was inserted, 0 if the date already existed.

    Example:
        conn = get_connection()
        fc = grid_to_swaths(...)
        count = insert_swaths(conn, fc, "2024-05-22")
        # count = 1  (one row for the whole day)
    """
    features = feature_collection.get("features", [])
    if not features:
        logger.warning("insert_swaths called with 0 features for %s — nothing inserted", valid_date)
        return 0

    # All features share the same metadata — grab it from the first feature
    sample = features[0]["properties"]

    sql = """
        INSERT INTO hail_swaths (features, product, valid_date, start_time, end_time, source_files)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (valid_date) DO NOTHING
    """

    with conn.cursor() as cur:
        cur.execute(sql, (
            json.dumps(features),
            sample["product"],
            valid_date,
            sample["start_time"],
            sample["end_time"],
            sample["source_files"],
        ))

    conn.commit()
    logger.info(
        "Inserted 1 row for %s (%d total polygons across all thresholds)",
        valid_date, len(features),
    )
    return 1


def get_swaths(
    conn,
    valid_date: str,
    thresholds: list[float] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict:
    """Fetch hail swaths from the DB and return them as a GeoJSON FeatureCollection.

    Args:
        conn: An open psycopg2 connection.
        valid_date: Date to query, e.g. "2024-05-22".
        thresholds: Optional list of threshold values to filter by (e.g. [0.75, 1.0]).
                    If None, all polygons for that date are returned.
        bbox: Optional bounding box (minLon, minLat, maxLon, maxLat).
              If provided, polygons are clipped to that box using Shapely.

    Returns:
        GeoJSON FeatureCollection dict.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT features FROM hail_swaths WHERE valid_date = %s",
            (valid_date,),
        )
        row = cur.fetchone()

    if row is None:
        return {"type": "FeatureCollection", "features": []}

    all_features = row[0]

    # Filter by threshold in Python if specific thresholds were requested
    if thresholds:
        threshold_set = set(thresholds)
        all_features = [f for f in all_features if f["properties"]["threshold"] in threshold_set]

    if bbox is not None:
        all_features = _clip_features_to_bbox(all_features, bbox)

    logger.info("Fetched %d polygons for %s", len(all_features), valid_date)
    return {"type": "FeatureCollection", "features": all_features}


def _clip_features_to_bbox(
    features: list[dict],
    bbox: tuple[float, float, float, float],
) -> list[dict]:
    """Filter and clip a list of GeoJSON features to a bounding box.

    Features that don't intersect the bbox are dropped.
    Features that partially overlap are clipped to the bbox boundary.

    Args:
        features: List of GeoJSON Feature dicts.
        bbox: (minLon, minLat, maxLon, maxLat) in WGS84.

    Returns:
        Filtered and clipped list of features.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    clip_box = box(min_lon, min_lat, max_lon, max_lat)

    result = []
    for feature in features:
        geom = make_valid(shape(feature["geometry"]))
        if not geom.intersects(clip_box):
            continue
        clipped = geom.intersection(clip_box)
        if clipped.is_empty:
            continue
        clipped_feature = dict(feature)
        clipped_feature["geometry"] = mapping(clipped)
        result.append(clipped_feature)

    return result

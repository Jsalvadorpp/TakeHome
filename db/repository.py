"""Read and write hail swaths to/from Postgres.

These functions are used by:
- pipeline/transformer.py  → insert_swaths() to store processed data
- api/                     → swaths_exist() + get_swaths() to serve the web viewer

Storage design: one row per threshold per date (5 rows per day).
Each row stores ALL polygons for that threshold as a single JSONB array.
This is much more compact than one row per polygon (which can be thousands).

No PostGIS required. Geometry is stored as plain JSONB.
Bounding box filtering is done in Python using Shapely.
"""

import json
import logging

from shapely.geometry import box, mapping, shape
from shapely.validation import make_valid

logger = logging.getLogger(__name__)


def create_tables(conn) -> None:
    """Create the hail_swaths table and indexes if they don't already exist.

    Safe to call every time the app starts — uses IF NOT EXISTS so it only
    creates the table on the first run and does nothing on subsequent runs.

    Schema: one row per (valid_date, threshold) pair — 5 rows per day.

    Args:
        conn: An open psycopg2 connection.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hail_swaths (
                id           SERIAL PRIMARY KEY,
                features     JSONB        NOT NULL,  -- all polygons for this threshold (JSON array)
                threshold    FLOAT        NOT NULL,  -- hail size in inches (e.g. 0.75)
                product      TEXT         NOT NULL,  -- MRMS product name
                valid_date   DATE         NOT NULL,  -- calendar date this swath covers
                start_time   TIMESTAMPTZ,
                end_time     TIMESTAMPTZ,
                source_files TEXT[],
                created_at   TIMESTAMPTZ  DEFAULT NOW(),
                UNIQUE (valid_date, threshold)       -- one row per date+threshold, no duplicates
            );
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS hail_swaths_date_threshold_idx
                ON hail_swaths (valid_date, threshold);
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
    """Insert one row per threshold into the DB.

    Groups all polygons by threshold and stores them together in a single row,
    so a full day of data for 5 thresholds = exactly 5 rows in the database.

    Uses ON CONFLICT DO NOTHING so running it twice for the same date is safe.

    Args:
        conn: An open psycopg2 connection.
        feature_collection: GeoJSON FeatureCollection dict (from grid_to_swaths).
        valid_date: The calendar date these swaths cover, e.g. "2024-05-22".

    Returns:
        Number of rows inserted (one per threshold, typically 5).

    Example:
        conn = get_connection()
        fc = grid_to_swaths(...)
        count = insert_swaths(conn, fc, "2024-05-22")
        # count = 5  (one row per threshold)
    """
    features = feature_collection.get("features", [])
    if not features:
        logger.warning("insert_swaths called with 0 features for %s — nothing inserted", valid_date)
        return 0

    # Group all polygons by their threshold value
    by_threshold: dict[float, list] = {}
    for feature in features:
        t = feature["properties"]["threshold"]
        if t not in by_threshold:
            by_threshold[t] = []
        by_threshold[t].append(feature)

    # All features share the same metadata — grab it from the first feature
    sample = features[0]["properties"]

    sql = """
        INSERT INTO hail_swaths (features, threshold, product, valid_date, start_time, end_time, source_files)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (valid_date, threshold) DO NOTHING
    """

    with conn.cursor() as cur:
        for threshold, threshold_features in by_threshold.items():
            cur.execute(sql, (
                json.dumps(threshold_features),
                threshold,
                sample["product"],
                valid_date,
                sample["start_time"],
                sample["end_time"],
                sample["source_files"],
            ))

    conn.commit()
    logger.info(
        "Inserted %d threshold rows for %s (%d total polygons)",
        len(by_threshold), valid_date, len(features),
    )
    return len(by_threshold)


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
                    If None, all thresholds for that date are returned.
        bbox: Optional bounding box (minLon, minLat, maxLon, maxLat).
              If provided, polygons are clipped to that box using Shapely.

    Returns:
        GeoJSON FeatureCollection dict.
    """
    conditions = ["valid_date = %s"]
    params: list = [valid_date]

    if thresholds:
        placeholders = ", ".join(["%s"] * len(thresholds))
        conditions.append(f"threshold IN ({placeholders})")
        params.extend(thresholds)

    sql = f"""
        SELECT features
        FROM hail_swaths
        WHERE {" AND ".join(conditions)}
        ORDER BY threshold DESC
    """

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    # Each row contains a list of GeoJSON features for one threshold.
    # Flatten all rows into a single features list.
    all_features = []
    for (features_data,) in rows:
        all_features.extend(features_data)

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

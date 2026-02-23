-- Hail swath database schema
-- Run this once against your Postgres database before using the pipeline.
--
-- Requires the PostGIS extension. Install it with:
--   CREATE EXTENSION IF NOT EXISTS postgis;
--
-- Usage:
--   psql $DATABASE_URL -f db/schema.sql

-- One row per threshold per day — 5 rows per date (one per threshold level).
-- features stores ALL polygons for that threshold as a JSON array.
-- No PostGIS required.
CREATE TABLE IF NOT EXISTS hail_swaths (
    id           SERIAL PRIMARY KEY,
    features     JSONB        NOT NULL,              -- array of all GeoJSON polygons for this threshold
    threshold    FLOAT        NOT NULL,              -- hail size in inches (e.g. 0.75)
    product      TEXT         NOT NULL,              -- MRMS product (e.g. MESH_Max_1440min)
    valid_date   DATE         NOT NULL,              -- calendar date this swath covers
    start_time   TIMESTAMPTZ,                        -- start of the processing window
    end_time     TIMESTAMPTZ,                        -- end of the processing window
    source_files TEXT[],                             -- original GRIB2 filenames
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (valid_date, threshold)                   -- prevents duplicate inserts
);

-- Index for date + threshold lookups (the most common query pattern).
CREATE INDEX IF NOT EXISTS hail_swaths_date_threshold_idx
    ON hail_swaths (valid_date, threshold);
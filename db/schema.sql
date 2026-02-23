-- Hail swath database schema
-- Run this once against your Postgres database before using the pipeline.
--
-- Usage:
--   psql $DATABASE_URL -f db/schema.sql

-- One row per date. All polygons for all thresholds are stored together
-- in a single JSONB array. Each polygon feature carries its own `threshold`
-- property so the API can still filter by threshold when reading.
-- No PostGIS required.
CREATE TABLE IF NOT EXISTS hail_swaths (
    id           SERIAL PRIMARY KEY,
    features     JSONB        NOT NULL,              -- flat array of all GeoJSON polygons for this date
    product      TEXT         NOT NULL,              -- MRMS product (e.g. MESH_Max_1440min)
    valid_date   DATE         NOT NULL,              -- calendar date this swath covers
    start_time   TIMESTAMPTZ,                        -- start of the processing window
    end_time     TIMESTAMPTZ,                        -- end of the processing window
    source_files TEXT[],                             -- original GRIB2 filenames
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (valid_date)                              -- one row per date, no duplicates
);

-- Index for date lookups (the primary query pattern).
CREATE INDEX IF NOT EXISTS hail_swaths_date_idx
    ON hail_swaths (valid_date);

-- Hail swath database schema
-- Run this once against your Postgres database before using the pipeline.
--
-- Usage:
--   psql $DATABASE_URL -f db/schema.sql

-- Requires PostGIS (provided by the postgis/postgis Docker image).
CREATE EXTENSION IF NOT EXISTS postgis;

-- One row per date. Two geometry representations stored side by side:
--   features  (JSONB)    — full GeoJSON array used by the API
--   geometry  (GEOMETRY) — union of all polygons as a PostGIS type for DBeaver map view
CREATE TABLE IF NOT EXISTS hail_swaths (
    id           SERIAL PRIMARY KEY,
    features     JSONB        NOT NULL,              -- flat array of all GeoJSON polygons for this date
    geometry     GEOMETRY(Geometry, 4326),                     -- union of all polygons (for DBeaver map visualization)
    product      TEXT         NOT NULL,              -- MRMS product (e.g. MESH_Max_1440min)
    valid_date   DATE         NOT NULL,              -- calendar date this swath covers
    start_time   TIMESTAMPTZ,                        -- start of the processing window
    end_time     TIMESTAMPTZ,                        -- end of the processing window
    source_files TEXT[],                             -- original GRIB2 filenames
    created_at   TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE (valid_date)                              -- one row per date, no duplicates
);

-- Index for date lookups
CREATE INDEX IF NOT EXISTS hail_swaths_date_idx
    ON hail_swaths (valid_date);

-- Spatial index for geometry queries
CREATE INDEX IF NOT EXISTS hail_swaths_geometry_idx
    ON hail_swaths USING GIST (geometry);
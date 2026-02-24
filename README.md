# MRMS Hail Exposure Swath Prototype

![coverage](https://img.shields.io/badge/coverage-86%25-green)

Fetches public NOAA MRMS hail radar data, builds GeoJSON polygons showing where radar estimated hail of a given size, and serves them through a local API with a map viewer.

> **Note:** This shows **hail exposure areas** based on radar estimates — not confirmed property damage.

---

## MRMS Product

**Product:** MESH_Max_1440min_00.50 (Maximum Estimated Size of Hail — 1440-minute / 24-hour rolling max)

- **S3 Path:** `s3://noaa-mrms-pds/CONUS/MESH_Max_1440min_00.50/YYYYMMDD/`
- **Why:** This is the 1440-minute (24-hour) rolling maximum MESH product. Each grid cell already contains the largest hail diameter estimated over the previous 24 hours, making it ideal for building full-day swath footprints without manual compositing. Files are generated every 2 minutes.
- **Resolution:** ~0.01° (~1 km) lat/lon grid, WGS84
- **Format:** Gzipped GRIB2 (`.grib2.gz`), ~80–230 KB per file
- **File naming:** `MRMS_MESH_Max_1440min_00.50_YYYYMMDD-HHMMSS.grib2.gz`

**Test Event:** May 22, 2024

- **Date:** 2024-05-22
- **Region:** US Great Plains (severe hail outbreak with multiple supercells)
- **Full time window:** `2024-05-22T18:00:00Z` to `2024-05-22T23:59:00Z` (180 files)
- **Quick time window:** `2024-05-22T20:00:00Z` to `2024-05-22T22:00:00Z` (60 files)

---

## Project Structure

```
mrms-hail-swaths/
├── ingest/            # Downloads MRMS files from S3, caches locally
│   └── fetcher.py
├── processing/        # Decodes GRIB2, applies thresholds, creates polygons
│   ├── decoder.py
│   └── polygonize.py
├── pipeline/          # Orchestrates ingest + processing + DB for one day
│   └── transformer.py
├── api/               # FastAPI server with swath endpoints
│   └── main.py
├── scripts/           # CLI tools for batch operations
│   └── ingester.py    # Backfills the last 5 years into Postgres
├── web/               # Next.js map viewer (MapLibre GL JS)
├── tests/             # Pytest test suite
├── cache/             # Downloaded MRMS files (not committed)
├── demo.py            # CLI script to generate a .geojson file
├── requirements.txt
├── Dockerfile
└── README.md
```

---

## Quick Start

### Option 1: Docker

```bash
docker compose up
```

The API will be running at `http://localhost:8000`.

### Option 2: Local Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Start the API server:

```bash
uvicorn api.main:app --reload
```

### Run the Map Viewer

```bash
cd web
npm install
npm run dev
```

Opens at `http://localhost:3000`.

### Run Tests

```bash
pytest
```

Or with Docker:

```bash
docker compose run --rm api pytest
```

### Run Tests with Coverage

```bash
coverage run -m pytest
coverage report -m
```

This prints a per-file coverage table and an overall percentage to the terminal.
To update the badge in this README, replace the number in the `coverage-XX%25` part of the badge URL at the top of this file with the new percentage shown in the `TOTAL` line of the report.

### Run the Ingester (Backfill Last 5 Years)

The Ingester processes every day in a date range and stores results in Postgres. Days already in the database are skipped automatically, so it is safe to re-run.

```bash
# Backfill the last 5 years (default)
python scripts/ingester.py

# Custom date range
python scripts/ingester.py --start 2024-01-01 --end 2024-12-31

# Single day
python scripts/ingester.py --start 2024-05-22 --end 2024-05-22
```

Or with Docker:

```bash
docker compose run --rm api python scripts/ingester.py
```

Expected output:

```
INFO pipeline.transformer: DB miss for 2024-05-22 — starting S3 pipeline
INFO pipeline.transformer: Listed 1 S3 files in 1.2s
INFO pipeline.transformer: Inserted swath data for 2024-05-22 into DB
INFO scripts.ingester: [1/1] 2024-05-22 — done (47 features)

Done — 1/1 days completed, 0 failed.
```

### Run the Demo Script

```bash
python demo.py --start 2024-05-22T20:00:00Z --end 2024-05-22T22:00:00Z --output swaths.geojson
```

Or with Docker:

```bash
docker compose run --rm api python demo.py --start 2024-05-22T20:00:00Z --end 2024-05-22T22:00:00Z --output swaths.geojson
```

---

## API Endpoints

### Health Check

```bash
curl http://localhost:8000/health
```

Returns: `{"ok": true}`

### Get Swath Polygons

```bash
curl "http://localhost:8000/swaths?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z"
```

Returns a GeoJSON FeatureCollection with polygons for each hail size threshold.

**Optional parameters:**
- `thresholds` — comma-separated inches (default: `0.75,1.00,1.50,2.00`)
- `bbox` — bounding box as `minLon,minLat,maxLon,maxLat`
- `simplify` — geometry simplification tolerance (default: `0.005`)

### Download as File

```bash
curl -O "http://localhost:8000/swaths/file?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z"
```

Downloads a `.geojson` file.

---

## Demo Script

Generate a GeoJSON file without starting the API server:

```bash
python demo.py --start 2024-05-22T20:00:00Z --end 2024-05-22T22:00:00Z --output swaths.geojson
```

**Options:**
- `--start` — start time (required)
- `--end` — end time (required)
- `--output` — output file path (default: `swaths.geojson`)
- `--thresholds` — comma-separated inches (default: `0.75,1.00,1.50,2.00`)
- `--bbox` — bounding box as `minLon,minLat,maxLon,maxLat`

---

## Finding a Time Window With Data

MRMS data is public. Browse available files with:

```bash
aws s3 ls --no-sign-request s3://noaa-mrms-pds/CONUS/MESH_Max_1440min_00.50/
```

Drill into a specific date to see what's available:

```bash
aws s3 ls --no-sign-request s3://noaa-mrms-pds/CONUS/MESH_Max_1440min_00.50/20240522/
```

Look for dates in May or June — these tend to have severe hail events in the Great Plains. Larger file sizes (>150 KB) usually indicate significant hail activity.

---

## Documentation

For a detailed explanation of how the project works, see the [docs/README.md](docs/README.md).

---

## Limitations

- **Exposure, not damage.** These polygons show where radar estimated hail above a certain size. They do not represent confirmed property damage or insurance losses.
- **~1 km resolution.** The MRMS grid is approximately 0.01° (~1 km). Polygons are not building-level precise.
- **Radar artifacts.** MESH is a radar-derived estimate. False positives and false negatives are possible, especially near radar beam edges or in complex terrain.
- **Data availability.** MRMS files on S3 may be delayed, incomplete, or unavailable for some time periods. The system handles missing files gracefully but gaps in data mean gaps in coverage.
- **Simplified boundaries.** Polygon geometries are simplified for performance. The actual hail footprint boundary is more granular than what the polygons show.

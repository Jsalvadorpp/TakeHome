# Architecture

How the project is organized, what each file does, and how they connect.

---

## Big Picture

The project has five main parts:

```
[NOAA S3 Bucket]  →  [Ingest]  →  [Processing]  →  [Pipeline]  →  [API]  →  [Web Viewer]
   (radar files)     (download)   (convert to        (store in     (serve     (show on
                                   polygons)          Postgres)     as JSON)    a map)
```

1. **Ingest** downloads radar files from NOAA's public servers
2. **Processing** reads those files and turns them into map shapes
3. **Pipeline** orchestrates ingest + processing and stores results in Postgres
4. **API** runs a web server that queries the database and returns results
5. **Web Viewer** displays the results on an interactive map

The `scripts/` folder contains CLI tools that run the pipeline in batch — for example, the Ingester backfills the last 5 years of data into the database so the API can serve any date instantly.

---

## Folder Structure

```
TakeHome/
├── ingest/                 # Step 1: Download radar data
│   ├── __init__.py
│   └── fetcher.py          # Functions to list and download files from S3
│
├── processing/             # Step 2: Convert radar data to map shapes
│   ├── __init__.py
│   ├── decoder.py          # Read GRIB2 files into number grids
│   └── polygonize.py       # Turn number grids into GeoJSON polygons
│
├── pipeline/               # Step 3: Orchestrate ingest + processing + DB for one day
│   ├── __init__.py
│   └── transformer.py      # Transformer class — fetch one day, store in Postgres
│
├── api/                    # Step 4: Serve results over HTTP
│   ├── __init__.py
│   └── main.py             # FastAPI server with endpoints
│
├── scripts/                # Batch CLI tools
│   ├── __init__.py
│   └── ingester.py         # Ingester class — run Transformer for every day in a range
│
├── web/                    # Step 5: Browser-based map viewer
│   └── app/
│       ├── page.tsx         # The main (and only) page — the map
│       ├── layout.tsx       # Page wrapper (title, fonts)
│       └── globals.css      # Base styles
│
├── tests/                  # Test suite (mirrors source structure)
│   ├── ingest/
│   │   └── test_fetcher.py
│   ├── processing/
│   │   └── test_polygonize.py
│   ├── pipeline/
│   │   └── test_transformer.py
│   └── api/
│       └── test_main.py
│
├── cache/                  # Downloaded radar files (not in git)
├── demo.py                 # CLI script — run pipeline without the server
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container definition
├── docker-compose.yml      # One-command startup
└── README.md               # Quick start guide
```

---

## How the Files Connect

### ingest/fetcher.py

**What it does:** Talks to NOAA's S3 bucket to find and download radar files.

**Key functions:**
- `list_files(product, start, end)` — Asks S3 "what files exist between these two times?" Returns a list of file paths (called S3 keys).
- `fetch_file(s3_key)` — Downloads one file, decompresses it (they're gzipped), and saves it to the `cache/` folder. If the file was already downloaded before, it skips the download.

**Used by:** `api/main.py` and `demo.py`

---

### processing/decoder.py

**What it does:** Opens a downloaded GRIB2 radar file and converts it into a grid of numbers (a numpy array) where each number is a hail size in inches.

**Key function:**
- `decode_grib2(file_path)` — Returns three things:
  1. `data` — A 2D grid of hail sizes (3500 rows x 7000 columns for CONUS)
  2. `transform` — The math that maps pixel positions to latitude/longitude
  3. `metadata` — Extra info (grid shape, coordinate bounds, etc.)

**Important detail:** The raw files store hail size in millimeters. This function converts to inches (divides by 25.4).

**Used by:** `api/main.py` and `demo.py`

---

### processing/polygonize.py

**What it does:** Takes the grid of hail sizes and turns it into GeoJSON polygons — the shapes you see on the map.

**Key functions:**
- `grid_to_swaths(data, transform, thresholds, ...)` — The main function. For each threshold (0.75", 1.00", etc.), it:
  1. Creates a binary mask (which pixels are above the threshold?)
  2. Cleans up noise in the mask
  3. Traces the outlines of the "yes" areas to create polygon shapes
  4. Simplifies the shapes so they're not too jagged
  5. Attaches metadata (threshold value, time, source files) to each shape
  6. Returns everything as a GeoJSON FeatureCollection

- `composite_max(arrays)` — Combines multiple grids into one by keeping the highest value at each pixel. Used when we have multiple radar snapshots and want one combined picture.

**Used by:** `api/main.py` and `demo.py`

---

### pipeline/transformer.py

**What it does:** Ties ingest and processing together for a single calendar day and stores the result in Postgres. This is the single unit of work that both the API (on demand) and the Ingester (batch) rely on.

**How it works:** Given a date string like `"2024-05-22"`, it:
1. Checks whether that date is already in the database — if yes, returns immediately (no S3 call)
2. Lists and downloads the last MRMS file for that day from S3
3. Decodes the GRIB2 file into a hail-size grid
4. Polygonizes at all standard thresholds for the full CONUS grid (no bounding box)
5. Inserts one row into the `hail_swaths` table
6. Deletes the local GRIB2 file (data is now safely in the DB)

**Key class:** `Transformer` — instantiate once and call `run(date_str)` for each day.

**Used by:** `api/routers/swaths.py` and `scripts/ingester.py`

---

### scripts/ingester.py

**What it does:** Runs the Transformer for every day in a date range. The default range is the last 5 years. Days already in the database are skipped automatically, so re-running is safe.

**Key class:** `Ingester` — call `run()` with optional `start_date` and `end_date` arguments.

**Example output:**
```
[1/1825] Processing 2019-02-25 ...
[1/1825] 2019-02-25 — done (0 features)   ← no hail that day, stored as empty
[2/1825] Processing 2019-02-26 ...
...
Done — 1825/1825 days completed, 0 failed.
```

**Used by:** Operators running a one-time backfill or a scheduled nightly job.

---

### api/main.py

**What it does:** Runs a web server (using FastAPI) that accepts HTTP requests and returns hail polygon data.

**How it works:** When someone requests `/swaths?start_time=...&end_time=...`, it:

1. Parses and validates the parameters (time, thresholds, bbox)
2. **Checks Postgres** — if a row already exists for that calendar date, it filters by threshold + bbox in Python and returns immediately (no S3 call)
3. If no DB row exists yet, it runs the full pipeline:
   - Calls `list_files()` to find MRMS files on S3 for that day
   - Downloads **only the last file** (the 1440min product means the last file already contains the full-day max)
   - Calls `decode_grib2()` to read the file
   - Calls `grid_to_swaths()` at **all five thresholds** with **no bbox** (stores the full CONUS data)
   - Inserts one row into `hail_swaths` via `insert_swaths()`
   - Returns the result filtered to the user's requested thresholds and bbox

**Used by:** The web viewer (via HTTP) and anyone using `curl`

---

### web/app/page.tsx

**What it does:** The browser-based map viewer. A single React page that:
1. Creates a MapLibre GL JS map with satellite imagery
2. Calls the API to get hail polygon data
3. Draws the polygons on the map, colored by threshold
4. Clusters nearby polygons into locations and reverse-geocodes them to city/state names
5. Shows a sidebar with two tabs:
   - **Locations** — scrollable list of hail locations (click to fly to that spot on the map)
   - **Controls** — threshold checkboxes to show/hide layers, opacity slider
6. Lets users click polygons to see details in a popup

**Talks to:**
- `api/main.py` via `fetch("http://localhost:8000/swaths?...")`
- OpenStreetMap Nominatim API for reverse geocoding location names

---

### demo.py

**What it does:** A command-line script that runs the same pipeline as the API but writes the result to a `.geojson` file instead of serving it over HTTP. Useful for testing or generating data without starting a server.

**Example:**
```bash
docker compose run --rm api python demo.py \
  --start 2024-05-22T20:00:00Z \
  --end 2024-05-22T22:00:00Z \
  --output swaths.geojson
```

---

## Data Flow Diagram

### First request for a date (DB miss)

```
User opens http://localhost:3000
        │
        ▼
  web/app/page.tsx
  "Give me hail polygons for May 22, 2024"
        │
        ▼  (HTTP request)
  api/routers/swaths.py
  /swaths?start_time=2024-05-22T00:00:00Z&end_time=2024-05-23T00:00:00Z
        │
        ├──▶ db/repository.py → swaths_exist("2024-05-22") → False (not yet stored)
        │
        ├──▶ ingest/fetcher.py → list_files() → picks the last file of the day
        │
        ├──▶ ingest/fetcher.py → fetch_file() → Downloads 1 file to cache/
        │
        ├──▶ processing/decoder.py → decode_grib2() → 1 number grid (mm → inches)
        │
        ├──▶ processing/polygonize.py → grid_to_swaths() → GeoJSON (all 5 thresholds)
        │
        ├──▶ db/repository.py → insert_swaths() → 1 row stored in Postgres
        │
        ▼  (HTTP response — JSON filtered by user's thresholds + bbox)
  web/app/page.tsx
  Draws polygons on the satellite map
  (colored by threshold: yellow, amber, orange, red)
```

### Every later request for the same date (DB hit)

```
  /swaths?start_time=2024-05-22T00:00:00Z&...
        │
        ├──▶ db/repository.py → swaths_exist("2024-05-22") → True
        │
        ├──▶ db/repository.py → get_swaths() → filters by threshold + bbox in Python
        │
        ▼  (instant response — no S3, no decoding)
  web/app/page.tsx
```

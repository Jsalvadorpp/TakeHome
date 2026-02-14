# Architecture

How the project is organized, what each file does, and how they connect.

---

## Big Picture

The project has four main parts:

```
[NOAA S3 Bucket]  →  [Ingest]  →  [Processing]  →  [API]  →  [Web Viewer]
   (radar files)     (download)   (convert to      (serve     (show on
                                   polygons)        as JSON)    a map)
```

1. **Ingest** downloads radar files from NOAA's public servers
2. **Processing** reads those files and turns them into map shapes
3. **API** runs a web server that triggers the pipeline and returns results
4. **Web Viewer** displays the results on an interactive map

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
├── api/                    # Step 3: Serve results over HTTP
│   ├── __init__.py
│   └── main.py             # FastAPI server with endpoints
│
├── web/                    # Step 4: Browser-based map viewer
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

### api/main.py

**What it does:** Runs a web server (using FastAPI) that accepts HTTP requests and returns hail polygon data.

**How it works:** When someone requests `/swaths?start_time=...&end_time=...`, it:
1. Calls `list_files()` to find what radar files exist for that time window
2. Samples them down (one per hour is enough since files overlap)
3. Calls `fetch_file()` to download each one
4. Calls `decode_grib2()` to read each file
5. Calls `composite_max()` to combine them
6. Calls `grid_to_swaths()` to create polygons
7. Caches the result in memory so the next request is instant
8. Returns the GeoJSON to the caller

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

```
User opens http://localhost:3000
        │
        ▼
  web/app/page.tsx
  "Give me hail polygons for May 22, 2024"
        │
        ▼  (HTTP request)
  api/main.py
  /swaths?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z
        │
        ├──▶ ingest/fetcher.py → list_files() → "There are 61 files"
        │                                         (samples to 3)
        │
        ├──▶ ingest/fetcher.py → fetch_file() × 3 → Downloads to cache/
        │
        ├──▶ processing/decoder.py → decode_grib2() × 3 → 3 number grids
        │
        ├──▶ processing/polygonize.py → composite_max() → 1 combined grid
        │
        ├──▶ processing/polygonize.py → grid_to_swaths() → GeoJSON with 376 polygons
        │
        ▼  (HTTP response — JSON)
  web/app/page.tsx
  Draws 376 polygons on the satellite map
  (colored by threshold: yellow, amber, orange, red)
```

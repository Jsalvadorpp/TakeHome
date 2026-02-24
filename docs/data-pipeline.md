# Data Pipeline

A step-by-step walkthrough of how raw radar data becomes colored shapes on a map.

---

## The Input: What NOAA Gives Us

NOAA runs hundreds of weather radars across the US. Every 2 minutes, they produce a file that covers the entire continental US (CONUS). Each file is a grid — imagine a giant spreadsheet laid over a map — where each cell contains a number: **the estimated maximum hail size at that location over the past 24 hours (1440 minutes)**, in millimeters.

The files live in a public Amazon S3 bucket:
```
s3://noaa-mrms-pds/CONUS/MESH_Max_1440min_00.50/20240522/
```

Each file is named like:
```
MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2.gz
                            ^^^^^^^^ ^^^^^^
                            date     time (UTC)
```

The grid is **3500 rows by 7000 columns** — about 24.5 million cells. Each cell covers roughly 1 km x 1 km on the ground.

---

## Why `MESH_Max_1440min_00.50`?

NOAA publishes several MESH products with different time windows. Here are the options we had:

| Product | What it contains |
|---------|-----------------|
| `MESH` | A single instant snapshot — "hail right now" |
| `MESH_Max_30min` | Biggest hail at each spot over the last 30 minutes |
| `MESH_Max_60min` | Biggest hail at each spot over the last 60 minutes |
| `MESH_Max_120min` | Biggest hail over the last 2 hours |
| `MESH_Max_240min` | Biggest hail over the last 4 hours |
| **`MESH_Max_1440min`** | **Biggest hail over the last 24 hours (one full day)** |

We picked the 1440-minute (24-hour) version for two reasons:

1. **One file covers an entire day.** Each file already contains the maximum hail size over the past 24 hours. This means the last file of any calendar day is also its complete swath — we never need to download multiple files and combine them ourselves. The 24-hour product gives us a ready-made full-day swath for free.

2. **Perfect for daily backfill.** Since we store one swath per calendar day in the database, the 1440-minute product maps cleanly to our data model. The Ingester processes one day at a time, and a single GRIB2 file is all it needs.

The `_00.50` at the end means "0.50 km above ground level." This is the standard level for hail estimates that represent what actually reaches the ground (as opposed to hail higher up in the atmosphere that might melt before landing).

---

## Step 1: List Available Files

**Code:** `ingest/fetcher.py` → `list_files()`

Given a time window (e.g., May 22 2024, midnight to midnight UTC), we ask S3 "what files do you have?" S3 returns a list of filenames. We parse the timestamp from each filename and keep only the ones within our window.

For a full calendar day, there are up to 720 files (one every 2 minutes).

**Why only use the last file?** Since `MESH_Max_1440min` already contains the maximum hail across the entire previous 24 hours, the last file of the day is also the complete swath. Any earlier file is a subset of it. We only ever download and process that one last file — no compositing needed.

---

## Step 2: Download Files

**Code:** `ingest/fetcher.py` → `fetch_file()`

Each file is about 80–230 KB (compressed). We download them to a local `cache/` folder. If a file was already downloaded before, we skip it — this makes repeated requests fast.

The files are gzip-compressed (`.grib2.gz`). After downloading, we decompress them to plain `.grib2` files.

---

## Step 3: Decode GRIB2 to Numbers

**Code:** `processing/decoder.py` → `decode_grib2()`

GRIB2 is a specialized weather data format. We use the `cfgrib` library to read it. What we get back is a 2D array of numbers — one number per grid cell.

Three important conversions happen here:

1. **Units:** The raw values are in millimeters. We divide by 25.4 to get inches (since hail sizes in the US are typically discussed in inches).

2. **Longitudes:** The raw file uses a 0°–360° longitude system (where the US is at 230°–300°). We convert to the standard -180°/+180° system (where the US is at -130° to -60°).

3. **Missing values:** Some cells have a huge number (3.4 × 10³⁸) meaning "no data." We replace these with `NaN` (Not a Number) so they're ignored in calculations.

The output looks like:
```
[[ 0.0,  0.0,  0.0,  0.03, 0.05, ... ],    ← row 0 (northernmost)
 [ 0.0,  0.0,  0.04, 0.12, 0.08, ... ],    ← row 1
 [ 0.0,  0.5,  1.2,  2.1,  1.8,  ... ],    ← row 2 (storm here!)
 ...
 [ 0.0,  0.0,  0.0,  0.0,  0.0,  ... ]]    ← row 3499 (southernmost)
```

---

## Step 4: Polygonize (Grid → Shapes)

**Code:** `processing/polygonize.py` → `grid_to_swaths()`

This is the most complex step. For each threshold (0.75", 1.00", 1.50", 2.00"), we:

### 4a. Create a Binary Mask

Ask "is this cell's value >= the threshold?" for every cell. Result: a grid of true/false.

```
Hail grid:     [0.0, 1.2, 0.8, 2.1, 0.3]
Threshold 1.0: [ no, YES, no,  YES, no ]
```

### 4b. Clean Up Noise

The binary mask might have tiny isolated "yes" dots (radar noise) or small gaps in otherwise solid areas. We apply morphological cleanup:
- **Closing** fills small holes (a "no" surrounded by "yes" becomes "yes")
- **Opening** removes tiny specks (an isolated "yes" surrounded by "no" is removed)

### 4c. Trace the Outlines

We use the `rasterio.features.shapes()` function to trace around the "yes" areas and create polygon shapes. This is like using the "magic wand" tool in Photoshop — it finds the boundaries of connected regions.

### 4d. Validate and Simplify

The raw polygon edges follow the grid exactly, making them very jagged (staircase pattern). We:
1. Run `make_valid()` to fix any broken geometry
2. Simplify the edges (smooth out the staircase)
3. Run `make_valid()` again (simplification can sometimes break geometry)
4. Remove tiny polygons that are too small to matter

### 4e. Clip to Bounding Box (Optional)

If the user specified a bounding box (a rectangular area of interest), we cut the polygons to fit within that box.

### 4f. Attach Properties

Each polygon gets metadata:
```json
{
  "threshold": 1.0,
  "product": "MESH_Max_1440min",
  "start_time": "2024-05-22T00:00:00Z",
  "end_time": "2024-05-23T00:00:00Z",
  "source_files": ["MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2"],
  "created_at": "2024-05-22T23:00:00Z"
}
```

---

## The Output: GeoJSON Stored in Postgres

The final result is a GeoJSON FeatureCollection containing all the polygons for all thresholds. This is stored as a single row in the `hail_swaths` Postgres table (one row per calendar date).

For our test event (May 22, 2024, full day), the polygon counts at each threshold are roughly:

- Many polygons for >= 0.75" (small hail — largest area)
- Fewer for >= 1.00"
- Fewer still for >= 1.50"
- The fewest for >= 2.00" (severe hail — smallest area)

The higher the threshold, the fewer and smaller the polygons — which makes sense, because less area gets hit by very large hail.

When the API serves a request for this date, it queries the DB row and filters to only the thresholds and bounding box the user asked for. No S3 download or GRIB2 decoding happens on the second request.

---

## Batch Ingestion: Backfilling Historical Data

The steps above describe what happens **on demand** when the API receives a request. For historical data (e.g. the last 5 years), we run the same pipeline in batch using two classes:

### Transformer (`pipeline/transformer.py`)

Handles a single calendar day. Given a date like `"2024-05-22"`, it:
1. Checks the database — if the date is already stored, returns immediately (no S3 call)
2. Runs steps 1–6 above for that full day
3. Stores the result in Postgres (one row per date)
4. Deletes the local GRIB2 cache file

```python
from pipeline.transformer import Transformer

t = Transformer()
fc = t.run("2024-05-22")
print(f"{len(fc['features'])} polygons stored")
```

### Ingester (`scripts/ingester.py`)

Calls Transformer for every day in a date range. The default range is the last 5 years. Days already in the database are automatically skipped, so re-running is safe.

```bash
# Backfill the last 5 years
python scripts/ingester.py

# Custom range
python scripts/ingester.py --start 2024-01-01 --end 2024-12-31

# Single day
python scripts/ingester.py --start 2024-05-22 --end 2024-05-22
```

After the Ingester finishes, any API request for a date in that range is served instantly from Postgres — no S3 call, no GRIB2 decoding.

---

## Visual Summary

```
NOAA S3 Bucket
    │
    │  one .grib2.gz file (last file of the day — already a 24h rolling max)
    ▼
┌──────────────┐
│   Download   │  fetch_file()
│   & Cache    │  ~80-230 KB
└──────┬───────┘
       │  .grib2 file (decompressed)
       ▼
┌──────────────┐
│   Decode     │  decode_grib2()
│   GRIB2      │  mm → inches, fix coordinates
└──────┬───────┘
       │  numpy array (3500 x 7000 grid of numbers)
       ▼
┌──────────────┐
│  Polygonize  │  grid_to_swaths()
│  per         │  mask → cleanup → trace → simplify
│  threshold   │  (all 5 thresholds, full CONUS, no bbox clip)
└──────┬───────┘
       │  GeoJSON FeatureCollection
       ▼
┌──────────────┐
│   Postgres   │  insert_swaths()
│   (one row   │  one row per calendar date
│   per day)   │
└──────┬───────┘
       │  API queries DB, filters by threshold + bbox
       ▼
  Polygons served to the map or returned as JSON
```

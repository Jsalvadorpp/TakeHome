# Step 1 — Findings (Completed)

## Chosen Product: `MESH_Max_1440min_00.50`

- **S3 prefix:** `s3://noaa-mrms-pds/CONUS/MESH_Max_1440min_00.50/YYYYMMDD/`
- **Why:** Rolling 1440-minute (24-hour) maximum MESH. Each grid cell already contains the largest hail diameter estimated over the previous 24 hours — no manual compositing needed. 2-minute time resolution, ~720 files/day.

## Available MESH Products in Bucket

| Product | Description |
|---------|-------------|
| `MESH_00.50/` | Instantaneous MESH snapshots |
| `MESH_Max_30min_00.50/` | 30-min rolling max |
| `MESH_Max_60min_00.50/` | 60-min rolling max |
| `MESH_Max_120min_00.50/` | 120-min rolling max |
| `MESH_Max_240min_00.50/` | 240-min rolling max |
| `MESH_Max_360min_00.50/` | 360-min rolling max |
| **`MESH_Max_1440min_00.50/`** | **24-hr rolling max (chosen)** |

## File Naming Convention

```
MRMS_MESH_Max_1440min_00.50_YYYYMMDD-HHMMSS.grib2.gz
```

- Timestamps on even 2-minute intervals (00, 02, 04, ..., 58)
- Gzipped GRIB2 format
- ~80–230 KB compressed per file
- Data available from 2020-10-14 to present

## Test Event: May 22, 2024

- Severe hail outbreak across the US Great Plains with multiple supercells
- File sizes spike during 18:00–23:59 UTC indicating significant hail activity
- **Full window:** `2024-05-22T18:00:00Z` to `2024-05-22T23:59:00Z` (180 files)
- **Quick window:** `2024-05-22T20:00:00Z` to `2024-05-22T22:00:00Z` (60 files)

## Compositing Strategy

Since the product is already a 1440-min (24-hour) rolling max, a single file covers the full day. We sample every 720th file (720 files × 2 min = 1440 min) to avoid redundant downloads.

## Files Updated

- `README.md` — product info, test event, curl examples, S3 browse commands
- `ingest/fetcher.py` — `PRODUCT_PREFIX`, `FILENAME_PREFIX`, `TIMESTAMP_FORMAT` constants

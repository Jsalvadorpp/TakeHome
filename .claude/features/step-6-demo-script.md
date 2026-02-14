# Step 6 — Demo Script

## Goal
Create a CLI script that runs the full ingest → process → output pipeline and writes a `.geojson` file, without starting the API server.

## File to Create
- `demo.py` (project root)

## CLI Interface
```bash
python demo.py --start 2024-05-21T18:00:00Z --end 2024-05-21T23:00:00Z --output swaths.geojson
```

### Arguments
| Argument | Required | Description |
|----------|----------|-------------|
| `--start` | Yes | Start time in ISO8601 format |
| `--end` | Yes | End time in ISO8601 format |
| `--output` | No | Output file path (default: `swaths.geojson`) |
| `--thresholds` | No | Comma-separated thresholds in inches (default: `0.75,1.00,1.50,2.00`) |
| `--bbox` | No | Bounding box: `minLon,minLat,maxLon,maxLat` |

## Implementation Details

### Flow
1. Parse CLI arguments with `argparse`
2. Call `ingest.list_files()` for the time range
3. Call `ingest.fetch_file()` for each file
4. Call `processing.decode_grib2()` on each file
5. If multiple files, call `processing.composite_max()`
6. Call `processing.grid_to_swaths()` with thresholds
7. Write the resulting FeatureCollection to the output file as formatted JSON
8. Print summary: number of features, thresholds used, output path

### Error Handling
- If no files found: print warning and write empty FeatureCollection
- If decoding fails on some files: log warnings, continue with successful ones
- Exit with non-zero code only on fatal errors (bad arguments, write failure)

### Logging
- Print progress: "Fetching N files...", "Processing...", "Writing output..."
- Log timing for each phase

## Dependencies
- Standard library: `argparse`, `json`, `logging`
- `ingest` module (Step 2)
- `processing` module (Step 3)

## Depends On
- Step 2 (ingest module)
- Step 3 (processing module)

## Verification
```bash
# Generate swaths for the test event
python demo.py --start <TEST_START> --end <TEST_END> --output test_swaths.geojson

# Verify output
python -c "import json; fc = json.load(open('test_swaths.geojson')); print(f'{len(fc[\"features\"])} features')"
```
- Output file should be valid GeoJSON
- Features should have all required properties
- Running with `--help` should show usage

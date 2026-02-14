# Step 4 — API Module

## Goal
Build a FastAPI server with endpoints to query and retrieve hail swath polygons as GeoJSON.

## Files to Create
- `api/__init__.py`
- `api/main.py`

## Endpoints

| Endpoint | Method | Params | Returns |
|----------|--------|--------|---------|
| `/health` | GET | — | `{"ok": true}` |
| `/swaths` | GET | `start_time` (ISO8601, required), `end_time` (ISO8601, required), `thresholds` (comma-sep floats, optional), `bbox` (minLon,minLat,maxLon,maxLat, optional), `simplify` (float, optional) | GeoJSON FeatureCollection |
| `/swaths/file` | GET | same as `/swaths` | Downloadable `.geojson` file with `Content-Disposition: attachment` |

## Implementation Details

### Parameter Validation
- `start_time` and `end_time`: required, ISO8601 format, return 400 if missing or invalid
- `thresholds`: optional, comma-separated floats (default: `0.75,1.00,1.50,2.00`)
- `bbox`: optional, format `minLon,minLat,maxLon,maxLat`
- `simplify`: optional float tolerance (default: `0.005`)
- Return `400` for any invalid parameters with a descriptive message

### Request Flow
1. Validate parameters
2. Call `ingest.list_files()` → if empty, return `404` with message
3. Call `ingest.fetch_file()` for each file
4. Call `processing.decode_grib2()` on each file
5. If multiple files, call `processing.composite_max()`
6. Call `processing.grid_to_swaths()` with thresholds, bbox, simplify
7. Return GeoJSON FeatureCollection

### Caching
- Cache results keyed by `(product, start_time, end_time, bbox, thresholds)`
- Simple dict or `functools.lru_cache` for MVP
- Repeated identical queries should not reprocess

### Logging
- Log timing for fetch and process steps
- Log warnings for missing files or slow operations

### CORS
- Enable CORS middleware so the Next.js dev server (different port) can call the API
  ```python
  from fastapi.middleware.cors import CORSMiddleware
  app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
  ```

### Error Handling
- `404`: no MRMS files found for the time window
- `400`: invalid parameters
- `500`: unexpected processing errors (log traceback, return generic message)
- Never crash — return empty FeatureCollection with warning if processing fails partially

## Dependencies
- `fastapi`
- `uvicorn`
- Modules from Steps 2 and 3

## Depends On
- Step 2 (ingest module)
- Step 3 (processing module)

## Verification
- `curl http://localhost:8000/health` → `{"ok": true}`
- `curl "http://localhost:8000/swaths?start_time=...&end_time=..."` → valid GeoJSON
- `curl "http://localhost:8000/swaths/file?start_time=...&end_time=..."` → downloads `.geojson` file
- Missing params → 400 response
- Time window with no data → 404 response

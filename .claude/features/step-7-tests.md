# Step 7 — Tests

## Goal
Write a pytest test suite covering threshold masking, polygonization, ingest logic, and API parameter validation. All tests must run without network access using synthetic data.

## Files to Create
```
tests/
├── __init__.py
├── test_polygonize.py   # Threshold masking, GeoJSON output, geometry validity
├── test_ingest.py       # S3 key listing logic (mocked)
├── test_api.py          # FastAPI TestClient: /health, /swaths param validation
```

## Test Details

### `test_polygonize.py`
Tests for `processing/polygonize.py`:

1. **test_threshold_masking**
   - Create a synthetic numpy array (e.g., 20×20) with known values
   - Apply threshold — verify correct pixels are selected
   - E.g., array with values [0, 0.5, 1.0, 1.5, 2.0, 2.5] in known positions
   - Threshold at 1.0 → only pixels ≥ 1.0 should be in the mask

2. **test_polygonize_output_valid_geojson**
   - Create synthetic array with a cluster of high values
   - Run `grid_to_swaths()` → verify output is a valid FeatureCollection
   - Check that features have correct required properties: `threshold`, `product`, `start_time`, `end_time`, `source_files`, `created_at`

3. **test_geometry_validity**
   - Run `grid_to_swaths()` on synthetic data
   - Verify every geometry in output passes `shapely.validation.explain_validity()`

4. **test_multiple_thresholds**
   - Run with multiple thresholds → verify separate features for each threshold
   - Higher thresholds should produce fewer/smaller polygons

5. **test_empty_result**
   - All values below threshold → should return empty FeatureCollection (no crash)

6. **test_bbox_clipping**
   - Provide a bbox that clips part of the data → verify polygons are clipped

### `test_ingest.py`
Tests for `ingest/fetcher.py`:

1. **test_list_files_filters_by_time**
   - Mock S3 `list_objects_v2` response with known keys
   - Verify `list_files()` returns only keys within the time range

2. **test_fetch_file_caching**
   - Mock the download
   - Call `fetch_file()` twice → verify download only happens once

3. **test_list_files_empty**
   - Mock empty S3 response → verify returns empty list (no crash)

### `test_api.py`
Tests for `api/main.py` using FastAPI `TestClient`:

1. **test_health_endpoint**
   - GET `/health` → 200, `{"ok": true}`

2. **test_swaths_missing_params**
   - GET `/swaths` without `start_time` → 400 or 422

3. **test_swaths_invalid_time**
   - GET `/swaths?start_time=not-a-date&end_time=not-a-date` → 400

4. **test_swaths_valid_request**
   - Mock ingest + processing modules
   - GET `/swaths?start_time=...&end_time=...` → 200, valid GeoJSON structure

5. **test_swaths_no_data**
   - Mock `list_files` to return empty → 404

## Implementation Notes
- Use `pytest` as the test runner
- Use `unittest.mock` for mocking S3 and network calls
- Create synthetic numpy arrays with `numpy` — no real GRIB2 files needed
- Create synthetic `Affine` transforms for polygonize tests
- Use `fastapi.testclient.TestClient` for API tests
- All tests must work offline — no network access

## Dependencies
- `pytest`
- `numpy` (synthetic test data)
- `shapely` (geometry validation)
- `fastapi[testclient]` / `httpx`
- `unittest.mock` (standard library)

## Depends On
- Step 2 (ingest module — to test)
- Step 3 (processing module — to test)
- Step 4 (API module — to test)

## Verification
```bash
pytest tests/ -v
```
All tests should pass with no network access required.

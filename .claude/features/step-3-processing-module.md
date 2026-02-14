# Step 3 — Processing Module

## Goal
Build the `processing/` module to decode GRIB2 files, apply hail-size thresholds, polygonize binary masks into valid GeoJSON features, and optionally composite multiple timesteps.

## Files to Create
- `processing/__init__.py`
- `processing/decoder.py` — GRIB2 decoding
- `processing/polygonize.py` — threshold masking + polygonization

## API

### GRIB2 Decoder
```python
# processing/decoder.py
def decode_grib2(file_path: Path) -> tuple[np.ndarray, Affine, dict]:
    """Decode a GRIB2 file and return (data_array, affine_transform, metadata).

    Primary: cfgrib + xarray
    Fallback: pygrib or rasterio with GDAL GRIB driver
    """
```

### Polygonizer
```python
# processing/polygonize.py
THRESHOLDS_INCHES = [0.75, 1.00, 1.50, 2.00]

def grid_to_swaths(
    data: np.ndarray,
    transform: Affine,
    thresholds: list[float],
    bbox: tuple[float,float,float,float] | None = None,
    simplify_tolerance: float = 0.005,
    min_area_deg2: float = 1e-5,
) -> geojson.FeatureCollection:
    """Convert grid data to GeoJSON swath polygons at multiple thresholds."""
```

### Composite (if using instantaneous grids)
```python
def composite_max(arrays: list[np.ndarray]) -> np.ndarray:
    """Per-cell max across timesteps to build swath-like footprint."""
    return np.nanmax(np.stack(arrays), axis=0)
```

## Implementation Details

### GRIB2 Decoding
- Primary: `cfgrib` + `xarray`
  ```python
  ds = xr.open_dataset(path, engine='cfgrib', backend_kwargs={'indexpath': ''})
  ```
- Fallback: `pygrib` or `rasterio` with GDAL GRIB driver
- Extract: data array (numpy), lat/lon coordinates or affine transform, nodata mask
- MRMS grids are ~0.01° lat/lon (WGS84) — no reprojection needed. Confirm from metadata.

### Units
- MRMS MESH values may be in **millimeters**, not inches
- Check GRIB2 metadata for unit information
- Convert mm → inches if needed: `inches = mm / 25.4`
- Document which unit the thresholds use
- The 0.75" threshold is both the minimum cutoff and the lowest polygonization level

### Polygonization Pipeline (per threshold)
1. **Binary mask**: `data >= threshold`
2. **Morphological cleanup**: close then open (1-2 px kernel, `scipy.ndimage`)
3. **Polygonize**: `rasterio.features.shapes(mask, transform=transform)`
4. **Shapely conversion**: create geometries → `make_valid()`
5. **Simplify**: `simplify(tolerance)` → `make_valid()` again
6. **Filter**: drop polygons with area < `min_area_deg2`
7. **Clip**: if bbox provided, use `shapely.ops.clip_by_rect`
8. **Properties**: attach `threshold`, `product`, `start_time`, `end_time`, `max_value_in_polygon`, `source_files`, `created_at`

### Performance
- MRMS CONUS grids are ~7000×3500 pixels
- Clip to bbox EARLY (before polygonization) for performance
- If no bbox given, process full grid but log a warning if slow

### Geometry Validity
- Always `make_valid()` after polygonizing
- Always `make_valid()` after simplifying (simplification can create invalid geometries)

## Feature Properties (required on every Feature)
- `threshold` — hail-size threshold for this polygon
- `product` — MRMS product name (e.g., `"MESH"` or `"MESH_Max_60min"`)
- `start_time` — ISO8601 start of time window
- `end_time` — ISO8601 end of time window
- `source_files` — list of MRMS filenames consumed
- `created_at` — generation timestamp

## Dependencies
- `xarray`, `cfgrib` (primary GRIB2 decoding)
- `rasterio` (polygonization + fallback GRIB2)
- `shapely` (geometry operations)
- `numpy`
- `scipy` (morphological operations)
- `geojson` (output formatting)

## Depends On
- Step 1 (data discovery — know the product and units)
- Step 2 (ingest — provides local GRIB2 file paths)

## Verification
- Decode a real GRIB2 file from the test event — check array shape, transform, metadata
- Confirm units from metadata and convert if needed
- Run `grid_to_swaths()` on decoded data — should produce valid GeoJSON with polygons at each threshold
- Validate all output geometries with Shapely
- Check that feature properties are present and correct

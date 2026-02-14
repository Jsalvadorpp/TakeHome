"""Decode MRMS GRIB2 files into numpy arrays."""

import logging
from pathlib import Path

import numpy as np
import xarray as xr
from rasterio.transform import Affine

logger = logging.getLogger(__name__)

# MRMS MESH values are in millimeters. Convert to inches for thresholds.
MM_PER_INCH = 25.4

# MRMS uses a large float as the missing/nodata value
MRMS_MISSING_VALUE = 3.4028234663852886e+38


def decode_grib2(file_path: Path) -> tuple[np.ndarray, Affine, dict]:
    """Decode a GRIB2 file and return the data array, affine transform, and metadata.

    Returns:
        data: 2D numpy array of hail sizes in inches, with nodata set to NaN.
        transform: Affine transform mapping pixel coords to WGS84 lon/lat.
        metadata: Dict with grid info (shape, lat/lon bounds, units, etc).
    """
    ds = xr.open_dataset(
        str(file_path),
        engine="cfgrib",
        backend_kwargs={"indexpath": ""},
    )

    # The variable name is "unknown" for MRMS MESH products
    var_name = list(ds.data_vars)[0]
    data = ds[var_name].values.astype(np.float64)

    # Get coordinate arrays
    lats = ds.coords["latitude"].values
    lons = ds.coords["longitude"].values

    # Convert longitudes from 0-360 to -180/180 range
    # MRMS uses 230-300, which should be -130 to -60
    lons = np.where(lons > 180, lons - 360, lons)

    # Replace missing values with NaN
    data[data >= MRMS_MISSING_VALUE / 2] = np.nan

    # Replace negative values with NaN (no meaningful negative hail sizes)
    data[data < 0] = np.nan

    # Convert from millimeters to inches
    data = data / MM_PER_INCH

    # Build the affine transform
    # Latitude goes north-to-south (descending), longitude goes west-to-east
    lon_min = float(lons.min())
    lat_max = float(lats.max())
    lon_res = float(abs(lons[1] - lons[0]))
    lat_res = float(abs(lats[1] - lats[0]))

    # Affine: (pixel_width, 0, x_origin, 0, -pixel_height, y_origin)
    transform = Affine(lon_res, 0.0, lon_min - lon_res / 2,
                       0.0, -lat_res, lat_max + lat_res / 2)

    metadata = {
        "shape": data.shape,
        "lat_min": float(lats.min()),
        "lat_max": float(lats.max()),
        "lon_min": float(lon_min),
        "lon_max": float(lons.max()),
        "lat_res": lat_res,
        "lon_res": lon_res,
        "units": "inches",
        "original_units": "mm",
    }

    ds.close()

    logger.info(
        "Decoded %s: shape=%s, data range=%.2f-%.2f inches",
        file_path.name,
        data.shape,
        np.nanmin(data),
        np.nanmax(data),
    )

    return data, transform, metadata

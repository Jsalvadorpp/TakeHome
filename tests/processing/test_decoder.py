"""Tests for processing/decoder.py

These tests mock xarray to avoid needing real GRIB2 files. We create fake
datasets with known values to verify the decoder's conversions work correctly.
"""

import numpy as np
import pytest
from unittest.mock import Mock, patch
from pathlib import Path

from processing.decoder import decode_grib2, MM_PER_INCH, MRMS_MISSING_VALUE


def _make_fake_dataset(data_values, lats, lons):
    """Test helper: creates a fake xarray Dataset that looks like a GRIB2 file.

    This lets us test the decoder without needing real GRIB2 files. We mock the
    xarray.open_dataset() call to return this fake dataset instead.

    Args:
        data_values: 2D numpy array of hail sizes (in millimeters, as MRMS provides)
        lats: 1D array of latitude values
        lons: 1D array of longitude values (can be 0-360° range to test conversion)

    Returns:
        A mock object that behaves like an xarray Dataset
    """
    mock_dataset = Mock()

    # The data variable (MRMS uses "unknown" as the variable name)
    mock_var = Mock()
    mock_var.values = data_values
    mock_dataset.data_vars = {"unknown": mock_var}
    mock_dataset.__getitem__ = lambda self, key: mock_var

    # Coordinates
    mock_lat = Mock()
    mock_lat.values = lats
    mock_lon = Mock()
    mock_lon.values = lons

    mock_dataset.coords = {
        "latitude": mock_lat,
        "longitude": mock_lon,
    }

    mock_dataset.close = Mock()

    return mock_dataset


# --- Unit conversion tests ---


def test_converts_millimeters_to_inches():
    """Verify MRMS data (in mm) is correctly converted to inches.

    MRMS provides hail sizes in millimeters, but we use inches in the US.
    The conversion is: inches = millimeters / 25.4

    Example: 25.4 mm should become 1.0 inch
    """
    # Create fake data: 25.4 mm (= 1 inch) at every cell
    data_mm = np.full((3, 3), 25.4, dtype=np.float64)
    lats = np.array([40.0, 39.99, 39.98])
    lons = np.array([-100.0, -99.99, -99.98])

    fake_ds = _make_fake_dataset(data_mm, lats, lons)

    with patch("xarray.open_dataset", return_value=fake_ds):
        data, transform, metadata = decode_grib2(Path("fake.grib2"))

    # All values should be 1.0 inch
    assert np.allclose(data, 1.0), f"Expected 1.0 inch, got {data[0, 0]}"
    assert metadata["units"] == "inches"
    assert metadata["original_units"] == "mm"


def test_converts_longitudes_from_0_360_to_minus180_180():
    """Verify longitude coordinates are converted to standard -180/+180 range.

    MRMS uses 0-360° longitude (where US is at 230-300°). We convert to the
    standard -180/+180° system (where US is at -130 to -60°).

    Example: 270° should become -90°
    """
    data_mm = np.zeros((2, 2), dtype=np.float64)
    lats = np.array([40.0, 39.0])
    lons = np.array([270.0, 280.0])  # Should convert to -90, -80

    fake_ds = _make_fake_dataset(data_mm, lats, lons)

    with patch("xarray.open_dataset", return_value=fake_ds):
        data, transform, metadata = decode_grib2(Path("fake.grib2"))

    # Check metadata has converted longitudes
    assert metadata["lon_min"] == -90.0, f"Expected -90, got {metadata['lon_min']}"
    assert metadata["lon_max"] == -80.0, f"Expected -80, got {metadata['lon_max']}"


# --- Missing value handling tests ---


def test_replaces_missing_values_with_nan():
    """Verify MRMS missing values (huge floats) are replaced with NaN.

    MRMS uses 3.4e38 to indicate "no data here." We replace these with NaN
    so they're ignored in calculations (like np.nanmax).
    """
    # Create data with one missing value
    data_mm = np.array([
        [25.4, 50.8],
        [MRMS_MISSING_VALUE, 76.2]
    ], dtype=np.float64)

    lats = np.array([40.0, 39.0])
    lons = np.array([-100.0, -99.0])

    fake_ds = _make_fake_dataset(data_mm, lats, lons)

    with patch("xarray.open_dataset", return_value=fake_ds):
        data, transform, metadata = decode_grib2(Path("fake.grib2"))

    # The missing value should be NaN
    assert np.isnan(data[1, 0]), "Missing value should be NaN"
    # Other values should be converted normally
    assert data[0, 0] == pytest.approx(1.0)  # 25.4mm = 1 inch
    assert data[0, 1] == pytest.approx(2.0)  # 50.8mm = 2 inches


def test_replaces_negative_values_with_nan():
    """Verify negative hail sizes (invalid) are replaced with NaN.

    Hail sizes can't be negative. If we see negative values (maybe due to
    data corruption), replace them with NaN.
    """
    data_mm = np.array([
        [25.4, -10.0],  # Second value is invalid
        [50.8, 76.2]
    ], dtype=np.float64)

    lats = np.array([40.0, 39.0])
    lons = np.array([-100.0, -99.0])

    fake_ds = _make_fake_dataset(data_mm, lats, lons)

    with patch("xarray.open_dataset", return_value=fake_ds):
        data, transform, metadata = decode_grib2(Path("fake.grib2"))

    # Negative value should be NaN
    assert np.isnan(data[0, 1]), "Negative value should be NaN"
    # Other values should be normal
    assert data[0, 0] == pytest.approx(1.0)


# --- Affine transform tests ---


def test_affine_transform_maps_pixels_to_coordinates():
    """Verify the affine transform correctly maps pixel positions to lat/lon.

    The affine transform is a formula that converts (row, col) pixel positions
    to (longitude, latitude) coordinates. This is critical for placing polygons
    in the right geographic location.
    """
    data_mm = np.zeros((3, 3), dtype=np.float64)
    lats = np.array([40.0, 39.99, 39.98])  # Descending (north to south)
    lons = np.array([-100.0, -99.99, -99.98])  # Ascending (west to east)

    fake_ds = _make_fake_dataset(data_mm, lats, lons)

    with patch("xarray.open_dataset", return_value=fake_ds):
        data, transform, metadata = decode_grib2(Path("fake.grib2"))

    # Check pixel resolution
    assert metadata["lon_res"] == pytest.approx(0.01)
    assert metadata["lat_res"] == pytest.approx(0.01)

    # Check the transform places the grid correctly
    # The transform origin should account for pixel-center registration
    # (MRMS pixels represent centers, not corners)
    lon_origin = transform.c  # x-origin
    lat_origin = transform.f  # y-origin

    # Origin should be half a pixel west and north of the min/max values
    assert lon_origin == pytest.approx(-100.0 - 0.01/2)
    assert lat_origin == pytest.approx(40.0 + 0.01/2)


# --- Metadata tests ---


def test_metadata_contains_grid_info():
    """Verify decode_grib2 returns complete metadata about the grid.

    Callers need this metadata to understand the grid's shape, extent, and units.
    """
    data_mm = np.zeros((10, 20), dtype=np.float64)
    lats = np.linspace(40.0, 39.0, 10)
    lons = np.linspace(-100.0, -99.0, 20)

    fake_ds = _make_fake_dataset(data_mm, lats, lons)

    with patch("xarray.open_dataset", return_value=fake_ds):
        data, transform, metadata = decode_grib2(Path("fake.grib2"))

    # Check all required metadata fields exist
    required_keys = {
        "shape", "lat_min", "lat_max", "lon_min", "lon_max",
        "lat_res", "lon_res", "units", "original_units"
    }
    assert set(metadata.keys()) == required_keys, f"Missing metadata: {required_keys - set(metadata.keys())}"

    # Check values are correct
    assert metadata["shape"] == (10, 20)
    assert metadata["lat_min"] == pytest.approx(39.0)
    assert metadata["lat_max"] == pytest.approx(40.0)
    assert metadata["lon_min"] == pytest.approx(-100.0)
    assert metadata["lon_max"] == pytest.approx(-99.0)

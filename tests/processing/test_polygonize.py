"""Tests for processing/polygonize.py"""

import numpy as np
from rasterio.transform import Affine
from shapely.geometry import shape
from shapely.validation import explain_validity

from processing.polygonize import grid_to_swaths, composite_max


# A simple affine transform: 0.01 degree pixels, origin at (-100, 40)
SAMPLE_TRANSFORM = Affine(0.01, 0.0, -100.0, 0.0, -0.01, 40.0)


def _make_grid(rows=20, cols=20):
    """Create a 20x20 grid with a block of high values in the center.

    Layout (values in inches):
        - Outer ring: 0.0
        - Middle ring (rows 4-15, cols 4-15): 1.0
        - Inner ring (rows 7-12, cols 7-12): 2.0
        - Core (rows 9-10, cols 9-10): 3.0
    """
    data = np.zeros((rows, cols), dtype=np.float64)
    data[4:16, 4:16] = 1.0
    data[7:13, 7:13] = 2.0
    data[9:11, 9:11] = 3.0
    return data


# --- Threshold masking ---


def test_threshold_selects_correct_pixels():
    """Given known values, the correct pixels should be above each threshold."""
    data = _make_grid()

    assert (data >= 0.75).sum() == 144  # 12x12 block
    assert (data >= 1.50).sum() == 36   # 6x6 block
    assert (data >= 2.50).sum() == 4    # 2x2 core


# --- GeoJSON output ---


def test_output_is_valid_feature_collection():
    """grid_to_swaths should return a valid GeoJSON FeatureCollection."""
    data = _make_grid()
    fc = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0],
        product="MESH_test",
        start_time="2024-05-22T20:00:00Z",
        end_time="2024-05-22T21:00:00Z",
        source_files=["test.grib2"],
    )

    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0

    feature = fc["features"][0]
    assert feature["type"] == "Feature"
    assert "geometry" in feature
    assert "properties" in feature


def test_feature_has_required_properties():
    """Every feature must have the required properties."""
    data = _make_grid()
    fc = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0],
        product="MESH_test",
        start_time="2024-05-22T20:00:00Z",
        end_time="2024-05-22T21:00:00Z",
        source_files=["test.grib2"],
    )

    required_keys = {"threshold", "product", "start_time", "end_time", "source_files", "created_at"}
    for feature in fc["features"]:
        assert required_keys.issubset(feature["properties"].keys())
        assert feature["properties"]["threshold"] == 1.0
        assert feature["properties"]["product"] == "MESH_test"
        assert feature["properties"]["start_time"] == "2024-05-22T20:00:00Z"


# --- Geometry validity ---


def test_all_geometries_are_valid():
    """Every output geometry should pass Shapely's validity check."""
    data = _make_grid()
    fc = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0, 2.0],
    )

    for feature in fc["features"]:
        geom = shape(feature["geometry"])
        assert geom.is_valid, f"Invalid geometry: {explain_validity(geom)}"


# --- Multiple thresholds ---


def test_multiple_thresholds_produce_separate_features():
    """Higher thresholds should produce fewer polygons."""
    data = _make_grid()
    fc = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0, 2.0],
    )

    thresholds_in_output = [f["properties"]["threshold"] for f in fc["features"]]
    assert 1.0 in thresholds_in_output
    assert 2.0 in thresholds_in_output


# --- Empty result ---


def test_empty_result_when_all_below_threshold():
    """All values below threshold should return an empty FeatureCollection."""
    data = np.zeros((20, 20), dtype=np.float64)
    fc = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0],
    )

    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 0


def test_empty_result_with_all_nan():
    """All-NaN grid should return an empty FeatureCollection."""
    data = np.full((20, 20), np.nan)
    fc = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0],
    )

    assert len(fc["features"]) == 0


# --- Bbox clipping ---


def test_bbox_clips_polygons():
    """Polygons outside the bbox should be excluded."""
    data = _make_grid()

    # Full result (no bbox)
    fc_full = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0],
        simplify_tolerance=0,
        min_area_deg2=0,
    )

    # Clip to a small bbox that covers only part of the data
    # The data is at roughly (-100, 40) to (-99.80, 39.80)
    # Clip to the right half
    fc_clipped = grid_to_swaths(
        data=data,
        transform=SAMPLE_TRANSFORM,
        thresholds=[1.0],
        bbox=(-99.90, 39.80, -99.80, 40.0),
        simplify_tolerance=0,
        min_area_deg2=0,
    )

    # Clipped should have fewer or equal features
    full_area = sum(shape(f["geometry"]).area for f in fc_full["features"])
    clipped_area = sum(shape(f["geometry"]).area for f in fc_clipped["features"])
    assert clipped_area < full_area


# --- Composite max ---


def test_composite_max():
    """composite_max should return per-cell maximum across arrays."""
    a = np.array([[1.0, 2.0], [3.0, 4.0]])
    b = np.array([[5.0, 1.0], [1.0, 6.0]])

    result = composite_max([a, b])
    expected = np.array([[5.0, 2.0], [3.0, 6.0]])
    np.testing.assert_array_equal(result, expected)


def test_composite_max_with_nan():
    """composite_max should ignore NaN values."""
    a = np.array([[1.0, np.nan], [3.0, 4.0]])
    b = np.array([[np.nan, 2.0], [1.0, np.nan]])

    result = composite_max([a, b])
    expected = np.array([[1.0, 2.0], [3.0, 4.0]])
    np.testing.assert_array_equal(result, expected)

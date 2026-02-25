"""Tests for pipeline/transformer.py

All external dependencies (S3, GRIB2 decoding, Postgres) are mocked.
Each test runs independently in under a second.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from rasterio.transform import Affine

from pipeline.transformer import Transformer, _parse_date, _empty_feature_collection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_transform():
    """Return an Affine transform that looks like a real MRMS grid transform."""
    return Affine(0.01, 0, -130.0, 0, -0.01, 55.0)


def _make_fake_data():
    """Return a small numpy grid where some cells exceed hail thresholds."""
    data = np.full((10, 10), 0.5)   # 0.5 inches everywhere
    data[3, 3] = 1.5                 # one cell exceeds 1.0" threshold
    data[5, 5] = 2.5                 # one cell exceeds 2.0" threshold
    return data


def _make_fake_feature_collection():
    """Return a minimal GeoJSON FeatureCollection for use in mocks."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 41], [-100, 40]]],
                },
                "properties": {
                    "threshold": 1.0,
                    "product": "MESH_Max_1440min",
                    "start_time": "2024-05-22T00:00:00+00:00",
                    "end_time": "2024-05-23T00:00:00+00:00",
                    "source_files": ["MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2"],
                    "created_at": "2024-05-22T21:00:00+00:00",
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# Helper: patch all external calls used by Transformer.run()
# ---------------------------------------------------------------------------

def _make_patches(
    swaths_exist_return=False,
    list_files_return=None,
    fetch_file_return=None,
    decode_grib2_return=None,
    grid_to_swaths_return=None,
    insert_swaths_return=1,
    get_swaths_return=None,
):
    """Build a dict of patch targets and their return values.

    Defaults produce a successful happy-path result so tests only need to
    override the values they care about.
    """
    if list_files_return is None:
        list_files_return = ["CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2.gz"]

    if fetch_file_return is None:
        fetch_file_return = Path("cache/MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2")

    if decode_grib2_return is None:
        decode_grib2_return = (_make_fake_data(), _make_fake_transform(), {})

    if grid_to_swaths_return is None:
        grid_to_swaths_return = _make_fake_feature_collection()

    if get_swaths_return is None:
        get_swaths_return = _make_fake_feature_collection()

    return {
        "pipeline.transformer.get_connection": MagicMock(return_value=MagicMock()),
        "pipeline.transformer.create_tables": MagicMock(),
        "pipeline.transformer.swaths_exist": MagicMock(return_value=swaths_exist_return),
        "pipeline.transformer.list_files": MagicMock(return_value=list_files_return),
        "pipeline.transformer.fetch_file": MagicMock(return_value=fetch_file_return),
        "pipeline.transformer.decode_grib2": MagicMock(return_value=decode_grib2_return),
        "pipeline.transformer.grid_to_swaths": MagicMock(return_value=grid_to_swaths_return),
        "pipeline.transformer.insert_swaths": MagicMock(return_value=insert_swaths_return),
        "pipeline.transformer.get_swaths": MagicMock(return_value=get_swaths_return),
    }


def _apply_patches(patches: dict):
    """Start all patches and return them so tests can inspect call args."""
    started = {}
    for target, mock in patches.items():
        p = patch(target, mock)
        p.start()
        started[target] = (p, mock)
    return started


def _stop_patches(started: dict):
    """Stop all patches started by _apply_patches."""
    for p, _ in started.values():
        p.stop()


# ---------------------------------------------------------------------------
# _parse_date() unit tests
# ---------------------------------------------------------------------------


def test_parse_date_valid_format():
    """A correctly formatted date string should parse without error."""
    result = _parse_date("2024-05-22")
    assert result.year == 2024
    assert result.month == 5
    assert result.day == 22


def test_parse_date_invalid_format_raises_value_error():
    """A date string that is not YYYY-MM-DD should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid date"):
        _parse_date("22-05-2024")


def test_parse_date_non_date_string_raises_value_error():
    """A completely non-date string should raise ValueError."""
    with pytest.raises(ValueError):
        _parse_date("not-a-date")


# ---------------------------------------------------------------------------
# _empty_feature_collection() unit tests
# ---------------------------------------------------------------------------


def test_empty_feature_collection_has_correct_structure():
    """The empty FeatureCollection helper should return a valid GeoJSON structure."""
    fc = _empty_feature_collection()
    assert fc["type"] == "FeatureCollection"
    assert fc["features"] == []


# ---------------------------------------------------------------------------
# Transformer.run() — DB hit
# ---------------------------------------------------------------------------


def test_returns_from_db_when_data_already_exists():
    """If the date is already in the DB, run() should return DB data without calling S3."""
    expected = _make_fake_feature_collection()
    patches = _make_patches(swaths_exist_return=True, get_swaths_return=expected)
    started = _apply_patches(patches)

    try:
        fc = Transformer().run("2024-05-22")

        # Should return the DB data
        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 1

        # S3 should NOT have been called
        _, list_files_mock = started["pipeline.transformer.list_files"]
        list_files_mock.assert_not_called()

        # fetch_file should NOT have been called
        _, fetch_mock = started["pipeline.transformer.fetch_file"]
        fetch_mock.assert_not_called()
    finally:
        _stop_patches(started)


# ---------------------------------------------------------------------------
# Transformer.run() — S3 pipeline (DB miss)
# ---------------------------------------------------------------------------


def test_returns_empty_collection_when_no_s3_files_found():
    """When S3 returns no files for the date, run() should return an empty FeatureCollection."""
    patches = _make_patches(list_files_return=[])
    started = _apply_patches(patches)

    try:
        fc = Transformer().run("2024-05-22")
        assert fc["type"] == "FeatureCollection"
        assert fc["features"] == []
    finally:
        _stop_patches(started)


def test_returns_empty_collection_when_download_fails():
    """When fetch_file raises an exception, run() should return an empty FeatureCollection."""
    patches = _make_patches()
    patches["pipeline.transformer.fetch_file"] = MagicMock(side_effect=RuntimeError("network error"))
    started = _apply_patches(patches)

    try:
        fc = Transformer().run("2024-05-22")
        assert fc["type"] == "FeatureCollection"
        assert fc["features"] == []
    finally:
        _stop_patches(started)


def test_returns_empty_collection_when_decode_fails():
    """When decode_grib2 raises an exception, run() should return an empty FeatureCollection."""
    patches = _make_patches()
    patches["pipeline.transformer.decode_grib2"] = MagicMock(side_effect=Exception("bad grib2"))
    started = _apply_patches(patches)

    try:
        fc = Transformer().run("2024-05-22")
        assert fc["type"] == "FeatureCollection"
        assert fc["features"] == []
    finally:
        _stop_patches(started)


def test_full_pipeline_fetches_decodes_inserts_and_returns_features():
    """Happy path: run() should go through all pipeline steps and return features."""
    expected = _make_fake_feature_collection()
    patches = _make_patches(get_swaths_return=expected)
    started = _apply_patches(patches)

    try:
        fc = Transformer().run("2024-05-22")

        assert fc["type"] == "FeatureCollection"
        assert len(fc["features"]) == 1

        # Every step in the pipeline should have been called once
        for name in ["list_files", "fetch_file", "decode_grib2", "grid_to_swaths", "insert_swaths"]:
            _, mock = started[f"pipeline.transformer.{name}"]
            mock.assert_called_once()
    finally:
        _stop_patches(started)


def test_uses_only_last_s3_key_when_multiple_files_found():
    """When S3 returns multiple files, only the last one should be fetched and decoded."""
    keys = [
        "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-160000.grib2.gz",
        "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-180000.grib2.gz",
        "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2.gz",
    ]
    patches = _make_patches(list_files_return=keys)
    started = _apply_patches(patches)

    try:
        Transformer().run("2024-05-22")

        # fetch_file should have been called with the last key only
        _, fetch_mock = started["pipeline.transformer.fetch_file"]
        fetch_mock.assert_called_once_with(keys[-1])
    finally:
        _stop_patches(started)


def test_local_grib2_file_is_deleted_after_insert(tmp_path):
    """After inserting into DB, the local GRIB2 cache file should be deleted."""
    # Create a real temporary file so that path.exists() and path.unlink() work
    grib2_file = tmp_path / "MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2"
    grib2_file.write_bytes(b"fake grib2 content")

    patches = _make_patches(fetch_file_return=grib2_file)
    started = _apply_patches(patches)

    try:
        Transformer().run("2024-05-22")

        # The file should have been deleted after insert
        assert not grib2_file.exists()
    finally:
        _stop_patches(started)


def test_grid_to_swaths_called_with_all_thresholds_and_no_bbox():
    """Polygonization should always use all standard thresholds with bbox=None.

    This ensures the full CONUS data is stored in the DB so future API
    requests with any bbox can still be served without re-fetching from S3.
    """
    from processing.polygonize import THRESHOLDS_INCHES

    patches = _make_patches()
    started = _apply_patches(patches)

    try:
        Transformer().run("2024-05-22")

        _, swaths_mock = started["pipeline.transformer.grid_to_swaths"]
        call_kwargs = swaths_mock.call_args.kwargs

        assert call_kwargs["thresholds"] == THRESHOLDS_INCHES
        assert call_kwargs["bbox"] is None
    finally:
        _stop_patches(started)


def test_time_range_is_noon_to_noon_utc():
    """The window should start at noon UTC on the given date and end at noon UTC the next day."""
    patches = _make_patches()
    started = _apply_patches(patches)

    try:
        Transformer().run("2024-05-22")

        _, swaths_mock = started["pipeline.transformer.grid_to_swaths"]
        call_kwargs = swaths_mock.call_args.kwargs

        # start_time should be noon UTC on the requested date
        assert "2024-05-22T12:00:00" in call_kwargs["start_time"]
        # end_time should be noon UTC the next day (exactly 24 hours later)
        assert "2024-05-23T12:00:00" in call_kwargs["end_time"]
    finally:
        _stop_patches(started)

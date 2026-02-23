"""Tests for ingest/fetcher.py"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from ingest.fetcher import (
    _parse_timestamp_from_filename,
    _decompress_gz,
    list_files,
    fetch_file,
)


# --- Timestamp parsing ---


def test_parse_timestamp_from_full_path():
    filename = "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2.gz"
    result = _parse_timestamp_from_filename(filename)
    expected = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
    assert result == expected


def test_parse_timestamp_from_filename_only():
    filename = "MRMS_MESH_Max_1440min_00.50_20240522-143200.grib2.gz"
    result = _parse_timestamp_from_filename(filename)
    expected = datetime(2024, 5, 22, 14, 32, 0, tzinfo=timezone.utc)
    assert result == expected


def test_parse_timestamp_from_decompressed_filename():
    filename = "MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2"
    result = _parse_timestamp_from_filename(filename)
    expected = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
    assert result == expected


def test_parse_timestamp_bad_filename():
    result = _parse_timestamp_from_filename("not_a_valid_file.txt")
    assert result is None


# --- Decompression ---


def test_decompress_gz(tmp_path):
    import gzip

    # Create a fake .grib2.gz file
    gz_path = tmp_path / "test.grib2.gz"
    content = b"fake grib2 data"
    with gzip.open(gz_path, "wb") as f:
        f.write(content)

    result = _decompress_gz(gz_path)

    assert result == tmp_path / "test.grib2"
    assert result.exists()
    assert result.read_bytes() == content
    assert not gz_path.exists()  # .gz should be deleted


# --- list_files ---


def test_list_files_filters_by_time():
    """list_files should only return keys whose timestamps fall within the range."""
    fake_objects = [
        {"Key": "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-190000.grib2.gz"},
        {"Key": "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2.gz"},
        {"Key": "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-210000.grib2.gz"},
        {"Key": "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-220000.grib2.gz"},
    ]

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Contents": fake_objects}]

    mock_s3 = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator

    with patch("ingest.fetcher.get_s3_client", return_value=mock_s3):
        start = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 5, 22, 21, 0, 0, tzinfo=timezone.utc)
        keys = list_files("CONUS/MESH_Max_1440min_00.50", start, end)

    assert len(keys) == 2
    assert "20240522-200000" in keys[0]
    assert "20240522-210000" in keys[1]


def test_list_files_empty():
    """list_files should return an empty list when no files match."""
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Contents": []}]

    mock_s3 = MagicMock()
    mock_s3.get_paginator.return_value = mock_paginator

    with patch("ingest.fetcher.get_s3_client", return_value=mock_s3):
        start = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 5, 22, 21, 0, 0, tzinfo=timezone.utc)
        keys = list_files("CONUS/MESH_Max_1440min_00.50", start, end)

    assert keys == []


def test_list_files_s3_error_returns_empty():
    """list_files should return an empty list when S3 errors out."""
    mock_s3 = MagicMock()
    mock_s3.get_paginator.side_effect = Exception("S3 unreachable")

    with patch("ingest.fetcher.get_s3_client", return_value=mock_s3):
        start = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 5, 22, 21, 0, 0, tzinfo=timezone.utc)
        keys = list_files("CONUS/MESH_Max_1440min_00.50", start, end)

    assert keys == []


# --- fetch_file ---


def test_fetch_file_caching(tmp_path):
    """fetch_file should skip download if the decompressed file already exists."""
    cached_file = tmp_path / "MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2"
    cached_file.write_bytes(b"cached data")

    key = "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2.gz"
    result = fetch_file(key, cache_dir=tmp_path)

    assert result == cached_file


def test_fetch_file_downloads_and_decompresses(tmp_path):
    """fetch_file should download from S3 and decompress the .gz file."""
    import gzip

    key = "CONUS/MESH_Max_1440min_00.50/20240522/MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2.gz"
    content = b"fake grib2 data"

    def fake_download(bucket, s3_key, local_path):
        with gzip.open(local_path, "wb") as f:
            f.write(content)

    mock_s3 = MagicMock()
    mock_s3.download_file.side_effect = fake_download

    with patch("ingest.fetcher.get_s3_client", return_value=mock_s3):
        result = fetch_file(key, cache_dir=tmp_path)

    assert result.exists()
    assert result.suffix == ".grib2"
    assert result.read_bytes() == content

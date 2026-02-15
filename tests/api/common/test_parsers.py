"""Tests for api/common/parsers.py

These tests verify the shared parsing utilities work correctly with both
valid inputs and invalid inputs. Since parsers are pure functions, they're
easy to test without mocking.
"""

import pytest
from datetime import datetime, timezone

from api.common.parsers import parse_time, parse_thresholds, parse_bbox


# --- parse_time tests ---


def test_parse_time_with_z_suffix():
    """ISO8601 time with Z suffix should parse correctly to UTC."""
    result = parse_time("2024-05-22T20:00:00Z")

    expected = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
    assert result == expected
    assert result.tzinfo == timezone.utc


def test_parse_time_with_utc_offset():
    """ISO8601 time with +00:00 offset should parse correctly."""
    result = parse_time("2024-05-22T20:00:00+00:00")

    expected = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
    assert result == expected


def test_parse_time_without_timezone_assumes_utc():
    """ISO8601 time without timezone should be assumed UTC."""
    result = parse_time("2024-05-22T20:00:00")

    expected = datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)
    assert result == expected
    assert result.tzinfo == timezone.utc


def test_parse_time_with_invalid_format_raises_error():
    """Invalid time formats should raise ValueError with helpful message."""
    with pytest.raises(ValueError) as exc_info:
        parse_time("not-a-date")

    assert "Invalid time format" in str(exc_info.value)
    assert "not-a-date" in str(exc_info.value)


# --- parse_thresholds tests ---


def test_parse_thresholds_with_valid_string():
    """Comma-separated thresholds should parse to list of floats."""
    result = parse_thresholds("0.75,1.00,1.50,2.00")

    assert result == [0.75, 1.0, 1.5, 2.0]


def test_parse_thresholds_handles_whitespace():
    """Spaces around commas should be stripped."""
    result = parse_thresholds("1.0, 2.0 , 3.0")

    assert result == [1.0, 2.0, 3.0]


def test_parse_thresholds_with_none_returns_default():
    """None input should return the provided default."""
    result = parse_thresholds(None, default=[0.75, 1.0])

    assert result == [0.75, 1.0]


def test_parse_thresholds_with_none_and_no_default_returns_empty():
    """None input with no default should return empty list."""
    result = parse_thresholds(None)

    assert result == []


def test_parse_thresholds_with_single_value():
    """Single threshold value should work."""
    result = parse_thresholds("1.5")

    assert result == [1.5]


def test_parse_thresholds_with_invalid_values_raises_error():
    """Non-numeric values should raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        parse_thresholds("abc,def")

    assert "Invalid thresholds" in str(exc_info.value)
    assert "abc,def" in str(exc_info.value)


def test_parse_thresholds_with_mixed_valid_invalid_raises_error():
    """Mixed valid and invalid values should raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        parse_thresholds("1.0,bad,2.0")

    assert "Invalid thresholds" in str(exc_info.value)


# --- parse_bbox tests ---


def test_parse_bbox_with_valid_string():
    """Valid bbox string should parse to tuple of four floats."""
    result = parse_bbox("-100.0,35.0,-95.0,40.0")

    assert result == (-100.0, 35.0, -95.0, 40.0)


def test_parse_bbox_handles_whitespace():
    """Spaces around commas should be stripped."""
    result = parse_bbox("-100, 35 , -95 , 40")

    assert result == (-100.0, 35.0, -95.0, 40.0)


def test_parse_bbox_with_none_returns_none():
    """None input should return None (no bounding box)."""
    result = parse_bbox(None)

    assert result is None


def test_parse_bbox_with_integers():
    """Integer coordinates should be converted to floats."""
    result = parse_bbox("-100,35,-95,40")

    assert result == (-100.0, 35.0, -95.0, 40.0)
    assert all(isinstance(x, float) for x in result)


def test_parse_bbox_with_too_few_values_raises_error():
    """Bbox with fewer than 4 values should raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        parse_bbox("1,2,3")

    assert "bbox must have exactly 4 values" in str(exc_info.value)


def test_parse_bbox_with_too_many_values_raises_error():
    """Bbox with more than 4 values should raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        parse_bbox("1,2,3,4,5")

    assert "bbox must have exactly 4 values" in str(exc_info.value)


def test_parse_bbox_with_non_numeric_values_raises_error():
    """Non-numeric bbox values should raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        parse_bbox("a,b,c,d")

    assert "Invalid bbox" in str(exc_info.value)
    assert "a,b,c,d" in str(exc_info.value)


def test_parse_bbox_with_mixed_valid_invalid_raises_error():
    """Mixed valid and invalid bbox values should raise ValueError."""
    with pytest.raises(ValueError) as exc_info:
        parse_bbox("1,2,bad,4")

    assert "Invalid bbox" in str(exc_info.value)

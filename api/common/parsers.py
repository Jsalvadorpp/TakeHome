"""Shared parsing utilities for API and CLI tools.

These pure functions parse and validate input strings into structured types.
They're shared between the FastAPI web service and the demo.py CLI tool.
"""

from datetime import datetime, timezone


def parse_time(value: str) -> datetime:
    """Parse an ISO8601 time string into a timezone-aware UTC datetime.

    Example:
        Input:  "2024-05-22T20:00:00Z"
        Output: datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)

        Input:  "2024-05-22T20:00:00"
        Output: datetime(2024, 5, 22, 20, 0, 0, tzinfo=timezone.utc)

    Args:
        value: ISO8601 formatted time string (with or without Z suffix)

    Returns:
        Timezone-aware datetime in UTC

    Raises:
        ValueError: If the time string is not valid ISO8601 format
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError as e:
        raise ValueError(f"Invalid time format: {value}") from e


def parse_thresholds(value: str | None, default: list[float] | None = None) -> list[float]:
    """Parse comma-separated thresholds string into a list of floats.

    Example:
        Input:  "0.75,1.00,1.50,2.00"
        Output: [0.75, 1.0, 1.5, 2.0]

        Input:  "1.0, 2.0"  (spaces are okay)
        Output: [1.0, 2.0]

        Input:  None (with default=[0.75, 1.0])
        Output: [0.75, 1.0]

    Args:
        value: Comma-separated list of threshold values in inches
        default: Default thresholds to use if value is None

    Returns:
        List of threshold values as floats

    Raises:
        ValueError: If any threshold value is not a valid number
    """
    if value is None:
        return default if default is not None else []

    try:
        return [float(t.strip()) for t in value.split(",")]
    except ValueError as e:
        raise ValueError(f"Invalid thresholds: {value}") from e


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    """Parse bbox string (minLon,minLat,maxLon,maxLat) into a tuple.

    Example:
        Input:  "-100.0,35.0,-95.0,40.0"
        Output: (-100.0, 35.0, -95.0, 40.0)

        Input:  "-100, 35, -95, 40"  (spaces are okay)
        Output: (-100.0, 35.0, -95.0, 40.0)

        Input:  None
        Output: None

    Args:
        value: Comma-separated bounding box coordinates (minLon,minLat,maxLon,maxLat)

    Returns:
        Tuple of (min_lon, min_lat, max_lon, max_lat) or None if value is None

    Raises:
        ValueError: If bbox doesn't have exactly 4 values or values are not valid numbers
    """
    if value is None:
        return None

    try:
        parts = [float(p.strip()) for p in value.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must have exactly 4 values: minLon,minLat,maxLon,maxLat")
        return (parts[0], parts[1], parts[2], parts[3])
    except ValueError as e:
        # Re-raise with context if it's already a ValueError from our validation
        if "bbox must have" in str(e):
            raise
        # Otherwise wrap the float conversion error
        raise ValueError(f"Invalid bbox: {value}") from e

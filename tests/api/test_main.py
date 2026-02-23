"""Tests for api/main.py"""

from unittest.mock import patch, MagicMock

import geojson
import numpy as np
from fastapi.testclient import TestClient
from rasterio.transform import Affine

from api.main import app

client = TestClient(app)


# --- Health ---


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# --- Parameter validation ---


def test_swaths_missing_start_time():
    response = client.get("/swaths", params={"end_time": "2024-05-22T21:00:00Z"})
    assert response.status_code == 422  # FastAPI returns 422 for missing required params


def test_swaths_missing_end_time():
    response = client.get("/swaths", params={"start_time": "2024-05-22T20:00:00Z"})
    assert response.status_code == 422


def test_swaths_invalid_time_format():
    response = client.get("/swaths", params={
        "start_time": "not-a-date",
        "end_time": "also-not-a-date",
    })
    assert response.status_code == 400


def test_swaths_invalid_thresholds():
    with patch("api.routers.swaths.list_files", return_value=["fake_key"]):
        response = client.get("/swaths", params={
            "start_time": "2024-05-22T20:00:00Z",
            "end_time": "2024-05-22T21:00:00Z",
            "thresholds": "abc,def",
        })
    assert response.status_code == 400


def test_swaths_invalid_bbox():
    with patch("api.routers.swaths.list_files", return_value=["fake_key"]):
        response = client.get("/swaths", params={
            "start_time": "2024-05-22T20:00:00Z",
            "end_time": "2024-05-22T21:00:00Z",
            "bbox": "1,2,3",
        })
    assert response.status_code == 400


# --- No data ---


def test_swaths_no_data_returns_404():
    with patch("api.routers.swaths.list_files", return_value=[]):
        response = client.get("/swaths", params={
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-01T01:00:00Z",
        })
    assert response.status_code == 404


# --- Valid request ---


def _make_fake_fc():
    """Build a minimal valid FeatureCollection for mocking."""
    return geojson.FeatureCollection([
        geojson.Feature(
            geometry={"type": "Polygon", "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 41], [-100, 40]]]},
            properties={
                "threshold": 1.0,
                "product": "MESH_Max_1440min",
                "start_time": "2024-05-22T20:00:00Z",
                "end_time": "2024-05-22T21:00:00Z",
                "source_files": ["test.grib2"],
                "created_at": "2024-05-22T21:00:00Z",
            },
        )
    ])


def test_swaths_valid_request():
    """A valid request should return 200 with a GeoJSON FeatureCollection."""
    fake_fc = _make_fake_fc()

    with patch("api.routers.swaths._build_swaths", return_value=fake_fc):
        response = client.get("/swaths", params={
            "start_time": "2024-05-22T20:00:00Z",
            "end_time": "2024-05-22T21:00:00Z",
        })

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1


def test_swaths_file_returns_attachment():
    """The /swaths/file endpoint should return a downloadable file."""
    fake_fc = _make_fake_fc()

    with patch("api.routers.swaths._build_swaths", return_value=fake_fc):
        response = client.get("/swaths/file", params={
            "start_time": "2024-05-22T20:00:00Z",
            "end_time": "2024-05-22T21:00:00Z",
        })

    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert "swaths.geojson" in response.headers["content-disposition"]

"""Tests for background/daily_ingest_job.py

All external dependencies (Transformer, time.sleep) are mocked.
Each test runs independently in under a second.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from background.daily_ingest_job import DailyIngestJob, INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_feature_collection(feature_count=3):
    """Return a minimal GeoJSON FeatureCollection with the given number of features."""
    return {
        "type": "FeatureCollection",
        "features": [{"type": "Feature"} for _ in range(feature_count)],
    }


def _mock_transformer(feature_count=3):
    """Return a mock Transformer whose run() returns a fake FeatureCollection."""
    mock = MagicMock()
    mock.run.return_value = _make_fake_feature_collection(feature_count)
    return mock


# ---------------------------------------------------------------------------
# DailyIngestJob.run_once() tests
# ---------------------------------------------------------------------------


def test_run_once_processes_yesterday():
    """run_once() should call Transformer.run() with yesterday's date in YYYY-MM-DD format."""
    expected_yesterday = (date.today() - timedelta(days=1)).isoformat()

    with patch("background.daily_ingest_job.Transformer", return_value=_mock_transformer()):
        DailyIngestJob().run_once()

    # Capture the actual call inside the patch context
    with patch("background.daily_ingest_job.Transformer") as mock_cls:
        mock_cls.return_value = _mock_transformer()
        DailyIngestJob().run_once()
        mock_cls.return_value.run.assert_called_once_with(expected_yesterday)


def test_run_once_returns_dict_with_date_and_feature_count():
    """run_once() should return a dict containing 'date' and 'feature_count' keys."""
    with patch("background.daily_ingest_job.Transformer") as mock_cls:
        mock_cls.return_value = _mock_transformer(feature_count=5)
        result = DailyIngestJob().run_once()

    assert "date" in result
    assert "feature_count" in result


def test_run_once_returns_correct_feature_count():
    """run_once() feature_count should equal the number of features in the FeatureCollection."""
    with patch("background.daily_ingest_job.Transformer") as mock_cls:
        mock_cls.return_value = _mock_transformer(feature_count=7)
        result = DailyIngestJob().run_once()

    assert result["feature_count"] == 7


def test_run_once_returns_zero_features_when_transformer_returns_empty():
    """run_once() should return feature_count=0 when the Transformer finds no hail data."""
    with patch("background.daily_ingest_job.Transformer") as mock_cls:
        mock_cls.return_value = _mock_transformer(feature_count=0)
        result = DailyIngestJob().run_once()

    assert result["feature_count"] == 0


def test_run_once_date_is_yesterday():
    """The 'date' in the return value should be yesterday's date in YYYY-MM-DD format."""
    expected_yesterday = (date.today() - timedelta(days=1)).isoformat()

    with patch("background.daily_ingest_job.Transformer") as mock_cls:
        mock_cls.return_value = _mock_transformer()
        result = DailyIngestJob().run_once()

    assert result["date"] == expected_yesterday


# ---------------------------------------------------------------------------
# DailyIngestJob.start() tests
# ---------------------------------------------------------------------------


def test_start_calls_run_once_before_sleeping():
    """start() should call run_once() immediately, before the first sleep."""
    job = DailyIngestJob()
    call_order = []

    def fake_run_once():
        call_order.append("run_once")
        return {"date": "2024-05-22", "feature_count": 3}

    def fake_sleep(seconds):
        call_order.append("sleep")
        raise KeyboardInterrupt  # stop the loop after the first sleep

    with patch.object(job, "run_once", side_effect=fake_run_once):
        with patch("background.daily_ingest_job.time.sleep", side_effect=fake_sleep):
            with pytest.raises(KeyboardInterrupt):
                job.start()

    # run_once must come before sleep
    assert call_order.index("run_once") < call_order.index("sleep")


def test_start_sleeps_for_correct_interval():
    """start() should sleep for INTERVAL_SECONDS (24 hours) between runs."""
    job = DailyIngestJob()

    with patch.object(job, "run_once", return_value={"date": "2024-05-22", "feature_count": 3}):
        with patch("background.daily_ingest_job.time.sleep", side_effect=KeyboardInterrupt) as mock_sleep:
            with pytest.raises(KeyboardInterrupt):
                job.start()

    mock_sleep.assert_called_once_with(INTERVAL_SECONDS)


def test_start_continues_after_run_once_raises_exception():
    """start() should log the error and keep looping even if run_once() raises an exception."""
    job = DailyIngestJob()

    # First call fails, second call succeeds, third sleep stops the loop
    run_once_results = [
        RuntimeError("S3 temporarily unavailable"),
        {"date": "2024-05-22", "feature_count": 0},
    ]

    with patch.object(job, "run_once", side_effect=run_once_results) as mock_run:
        # First sleep passes, second sleep stops the loop
        with patch("background.daily_ingest_job.time.sleep", side_effect=[None, KeyboardInterrupt]):
            with pytest.raises(KeyboardInterrupt):
                job.start()

    # Both calls should have happened — the exception did not stop the loop
    assert mock_run.call_count == 2


def test_interval_seconds_is_24_hours():
    """INTERVAL_SECONDS should equal exactly 24 hours (86400 seconds)."""
    assert INTERVAL_SECONDS == 86400

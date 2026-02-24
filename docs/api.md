# API

How the backend server works and what you can ask it for.

---

## Overview

The API is a small Python web server built with FastAPI. It runs on `http://localhost:8000` and has three endpoints (URLs you can call).

You start it with:
```bash
docker compose up
```

---

## Endpoints

### GET /health

**What it does:** A simple "am I alive?" check.

**Example:**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{"ok": true}
```

Nothing else to it. If you get this response, the server is running.

---

### GET /swaths

**What it does:** This is the main endpoint. It returns hail swath polygons as GeoJSON. On the first request for a given date it runs the full pipeline (S3 → decode → polygonize) and stores the result in Postgres. Every subsequent request for that date is served directly from the database — no S3 call needed.

**Required parameters:**
| Parameter | Example | What it means |
|-----------|---------|---------------|
| `start_time` | `2024-05-22T20:00:00Z` | Beginning of the time window (ISO 8601 format, UTC) |
| `end_time` | `2024-05-22T22:00:00Z` | End of the time window |

**Optional parameters:**
| Parameter | Default | What it means |
|-----------|---------|---------------|
| `thresholds` | `0.50,0.75,1.00,1.50,2.00` | Which hail sizes to generate polygons for (comma-separated, in inches) |
| `bbox` | *(none — full CONUS)* | Only return polygons within this rectangle: `minLon,minLat,maxLon,maxLat` |
| `simplify` | `0.005` | How much to smooth polygon edges (higher = smoother but less accurate) |

**Example — basic request:**
```bash
curl "http://localhost:8000/swaths?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z"
```

**Example — only large hail in Texas:**
```bash
curl "http://localhost:8000/swaths?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z&thresholds=1.50,2.00&bbox=-107,25,-93,37"
```

**Response:** A GeoJSON FeatureCollection:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[-97.5, 35.0], [-97.4, 35.0], ...]]
      },
      "properties": {
        "threshold": 1.0,
        "product": "MESH_Max_1440min",
        "start_time": "2024-05-22T00:00:00Z",
        "end_time": "2024-05-23T00:00:00Z",
        "source_files": ["MRMS_MESH_Max_1440min_00.50_20240522-200000.grib2"],
        "created_at": "2024-05-22T23:00:00Z"
      }
    },
    ...
  ]
}
```

**How long does it take?**
- First request for a date: ~30–120 seconds (downloads from S3, decodes GRIB2, polygonizes, stores in Postgres)
- Any later request for the same date: instant (served from Postgres, no S3 call)

---

### GET /swaths/file

**What it does:** Exactly the same as `/swaths`, but returns the result as a downloadable `.geojson` file instead of inline JSON.

**Example:**
```bash
curl -O "http://localhost:8000/swaths/file?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z"
```

This saves a file called `swaths.geojson` to your current directory. You can open it in QGIS, geojson.io, or any GIS tool.

---

## Error Responses

| Status | When | Example |
|--------|------|---------|
| 400 | Bad parameters | Invalid date format, bad thresholds, wrong bbox format |
| 404 | No data found | No radar files exist for the given time window |
| 422 | Missing required parameters | Forgot `start_time` or `end_time` |
| 500 | Processing error | All files failed to decode (rare) |

Example error response:
```json
{
  "detail": "No MRMS files found for this time window."
}
```

---

## Caching

The API uses Postgres as its cache. The first time a date is requested, the full pipeline runs (S3 → decode → polygonize) and the result is stored in the `hail_swaths` table — one row per calendar date, containing all five threshold polygons for the full CONUS grid.

Every subsequent request for that date — regardless of which thresholds or bounding box the user asks for — is served from that one DB row. The threshold and bbox filtering happens in Python, not SQL, so no data is ever re-fetched or re-processed.

The cache survives server restarts (it lives in Postgres, not in memory). To pre-populate it for multiple dates at once, use the Ingester script.

---

## CORS

The API allows requests from any origin (`*`). This is needed because the web viewer runs on `http://localhost:3000` (a different port), and browsers block cross-origin requests by default.

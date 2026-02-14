# Step 8 — Dockerfile + README

## Goal
Create a Dockerfile for reliable GRIB2 processing and a comprehensive README with run instructions, curl examples, and limitations.

## Files to Create
- `Dockerfile`
- `docker-compose.yml` (optional but recommended for one-command startup)
- `README.md`
- `requirements.txt`

## Dockerfile

```dockerfile
FROM python:3.11-slim

# Install system dependencies for GRIB2 decoding
RUN apt-get update && apt-get install -y \
    libeccodes-dev \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Key points:
- Python 3.11-slim base
- `libeccodes-dev` for cfgrib/GRIB2 support
- `libgeos-dev` for Shapely
- Expose port 8000

## docker-compose.yml (optional)
```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./cache:/app/cache
```

## requirements.txt
```
fastapi
uvicorn[standard]
boto3
xarray
cfgrib
rasterio
shapely
numpy
geojson
scipy
```

## README.md Must Include

### 1. Project Overview
- What this does (MRMS hail exposure swath prototype)
- Exposure ≠ confirmed damage disclaimer

### 2. MRMS Product Choice
- Which product was chosen and why
- Exact S3 path prefix
- File naming convention

### 3. Quick Start
Two options:
```bash
# Option 1: Docker
docker compose up

# Option 2: Local venv
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload
```

Also how to run the Next.js viewer:
```bash
cd web && npm install && npm run dev
```

### 4. curl Examples
For each endpoint with the test event time window:
```bash
# Health check
curl http://localhost:8000/health

# Get swaths
curl "http://localhost:8000/swaths?start_time=YYYY-MM-DDTHH:MM:SSZ&end_time=YYYY-MM-DDTHH:MM:SSZ"

# Download file
curl -O "http://localhost:8000/swaths/file?start_time=...&end_time=..."
```

### 5. Demo Script Usage
```bash
python demo.py --start <START> --end <END> --output swaths.geojson
```

### 6. How to Find Data
```bash
aws s3 ls --no-sign-request s3://noaa-mrms-pds/<product-path>/
```

### 7. Running Tests
```bash
pytest tests/ -v
```

### 8. Limitations Section
- Exposure ≠ confirmed property damage
- ~0.01° grid resolution (~1 km) — not building-level precision
- Radar artifacts possible (false positives/negatives)
- Data availability and latency (MRMS data may be delayed or missing)
- Simplified polygon boundaries due to tolerance settings

## Depends On
- All previous steps (this wraps everything up)

## Verification
- `docker build -t mrms-hail .` succeeds
- `docker compose up` starts the API
- README instructions can be followed from scratch by a teammate in under 5 minutes
- All curl examples return expected results

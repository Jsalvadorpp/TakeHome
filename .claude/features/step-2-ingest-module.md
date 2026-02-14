# Step 2 — Ingest Module

## Goal
Build the `ingest/` module to fetch MRMS GRIB2 files from S3 for a given time range, with local caching.

## Files to Create
- `ingest/__init__.py`
- `ingest/fetcher.py`

## API

```python
# ingest/fetcher.py
from datetime import datetime
from pathlib import Path

def list_files(product: str, start: datetime, end: datetime) -> list[str]:
    """List S3 keys for MRMS product between start/end times.

    Parse timestamps from S3 key names to filter by time range.
    """

def fetch_file(s3_key: str, cache_dir: Path = Path("./cache")) -> Path:
    """Download file to local cache if not already present. Return local path.

    - Skip download if file already exists in cache
    - Decompress .gz files after download
    - Return path to the decompressed file
    """
```

## Implementation Details

### S3 Access
- Use `boto3` with unsigned config:
  ```python
  from botocore import UNSIGNED
  from botocore.config import Config
  s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
  ```
- Alternative: plain HTTPS GET to `https://noaa-mrms-pds.s3.amazonaws.com/<key>`

### Caching
- Cache directory: `./cache/`
- Key by filename (strip S3 prefix)
- Check existence before downloading
- Decompress `.gz` → `.grib2` after download

### Timestamp Parsing
- Parse the timestamp from the MRMS filename (it's embedded in the name)
- Do NOT rely on S3 `LastModified`
- Use parsed timestamps to filter files within the requested time range

### Error Handling
- Missing/unavailable files: log a warning, don't crash
- Network errors: retry once, then log and skip
- Return empty list from `list_files` if no files match (don't raise)

## Dependencies
- `boto3`
- Standard library: `gzip`, `pathlib`, `datetime`, `logging`

## Depends On
- Step 1 (need to know the exact S3 prefix and file naming convention)

## Verification
- Call `list_files()` with the test event time window — should return a non-empty list of S3 keys
- Call `fetch_file()` on one key — should download, decompress, and return a local `.grib2` path
- Call `fetch_file()` again on the same key — should skip download (cache hit)

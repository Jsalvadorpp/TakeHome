# Improvements & Notes

A running list of observations, known limitations, and ideas for future improvements.

---

## Database

### `start_time` / `end_time` columns are redundant
- These columns are stored in the DB and on each GeoJSON feature, but data lookup is keyed entirely off `valid_date`.
- The MRMS 1440min product already represents the full 24-hour max for a calendar day, so the time window is implicit.
- **Note**: DBeaver displays these timestamps in local timezone (e.g., UTC-5), so a row for `2024-05-22` will show `start_time = 2024-05-21 19:00:00 -0500` — this is correct, just a display timezone offset.
- **Possible improvement**: Remove `start_time`/`end_time` from the DB schema and keep them only on the GeoJSON feature properties (where the spec requires them).

---

## API

### First request for a new date is slow
- On a DB miss, the API fetches from S3, decodes GRIB2, polygonizes, and stores to DB before returning.
- Subsequent requests for the same date are fast (served from DB).
- **Possible improvement**: Pre-populate the DB nightly with a scheduled job so the first user request is never slow.

---

## Web Viewer

*(add notes here)*

---

## Processing

*(add notes here)*

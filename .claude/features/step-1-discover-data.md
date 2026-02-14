# Step 1 — Discover the Data

## Goal
Explore the NOAA MRMS S3 bucket, identify the correct MESH product, pick a test event, and verify data availability before writing any code.

## Tasks

1. **Explore the S3 bucket structure**
   ```bash
   aws s3 ls --no-sign-request s3://noaa-mrms-pds/
   ```
   Drill down into subdirectories to find the MESH product family.

2. **Find the MESH product path**
   - Preferred: `MESH_Max_60min` (max-over-time track grids)
   - Fallback: instantaneous MESH grids (will require compositing in Step 3)
   - Record the exact S3 prefix (e.g., `s3://noaa-mrms-pds/CONUS/MESHTrack/MESH_Max_60min/`)

3. **Document the file format**
   - File naming convention and embedded timestamps
   - Time resolution (e.g., every 2 minutes)
   - File format: expect gzipped GRIB2 (`.grib2.gz`)

4. **Pick a concrete test event**
   - Choose a recent severe hail day in the US Great Plains (May or June is ideal)
   - Verify files exist for that date:
     ```bash
     aws s3 ls --no-sign-request s3://noaa-mrms-pds/<product-path>/YYYYMMDD/
     ```
   - Record the specific date and time window

5. **Document findings**
   - Exact S3 prefix
   - File naming pattern
   - Chosen test event date and rationale
   - These will go into the README later (Step 8)

## Output
A clear record of:
- The chosen MRMS product and its S3 path
- The file naming convention
- A verified test event date with confirmed file availability

## Dependencies
None — this is the first step.

## Notes
- No code needs to be written in this step
- Do NOT proceed to other steps until data availability is confirmed
- The bucket is public, no credentials needed (`--no-sign-request`)

# MRMS Hail Exposure Swath Prototype

## Project Summary

A Python prototype that fetches public NOAA MRMS hail radar grids, converts them into GeoJSON "swath" polygons at size thresholds, and serves them via a local FastAPI API with a Next.js map viewer. No proprietary data, no API keys.

**Important**: The output represents **hail exposure areas** (where radar estimated hail of a given size), **not** confirmed property damage. This distinction must be reflected in code, API responses, and documentation.

## Code Style

- Write code that a **junior developer can read and understand**. Favor clarity over cleverness.
- Use plain, descriptive variable and function names. No abbreviations unless universally known.
- Keep functions short and single-purpose. If a function does more than one thing, split it.
- Add brief docstrings to public functions explaining what they do, not how.
- Avoid abstractions, wrappers, or indirection that don't earn their complexity. Flat is better than nested.
- Scripts and CLI commands should be **simple one-liners** — no chained pipes, no obscure flags, no bash wizardry.
- Prefer straightforward `if/else` over ternaries or clever boolean tricks.
- When in doubt, write the obvious thing.
- **Documentation & comments must be simple enough for a junior developer or new team member to understand without asking questions.** Always include concrete input/output examples where possible. Avoid jargon — if you must use a technical term, explain it in plain English.

## Testing Guidelines

- **Tests should be simple and readable.** A junior developer should be able to understand what's being tested and why just by reading the test function name and body.
- **Mock all external dependencies.** Tests must NOT depend on external connections (S3, APIs, network) or external files. Use mocks, fixtures, or in-memory test data instead.
- **Tests should be fast and isolated.** Each test should run independently in under a second. No shared state between tests.
- Use descriptive test function names that explain the scenario: `test_empty_result_when_all_below_threshold()` not `test_edge_case_1()`

## Architecture

```
mrms-hail-swaths/
├── ingest/       # Fetch MRMS GRIB2 files from public S3
├── processing/   # Decode GRIB2 → threshold → polygonize → GeoJSON
├── api/          # FastAPI server
├── web/          # Next.js app with Mapbox GL JS viewer
├── tests/
├── demo.py       # CLI script: generate swaths → dump GeoJSON file
├── requirements.txt
├── Dockerfile
└── README.md
```

## Implementation Steps

Detailed plans for each step live in `.claude/features/`:

1. **Discover the data** → [step-1-discover-data.md](.claude/features/step-1-discover-data.md)
2. **Ingest module** → [step-2-ingest-module.md](.claude/features/step-2-ingest-module.md)
3. **Processing module** → [step-3-processing-module.md](.claude/features/step-3-processing-module.md)
4. **API module** → [step-4-api-module.md](.claude/features/step-4-api-module.md)
5. **Web viewer** → [step-5-web-viewer.md](.claude/features/step-5-web-viewer.md)
6. **Demo script** → [step-6-demo-script.md](.claude/features/step-6-demo-script.md)
7. **Tests** → [step-7-tests.md](.claude/features/step-7-tests.md)
8. **Dockerfile + README** → [step-8-dockerfile-readme.md](.claude/features/step-8-dockerfile-readme.md)

Work through these in order. Each step's feature file has the full spec, dependencies, and verification steps.

## Constraints

- Python 3.11+, no paid services, no API keys
- All coordinates in WGS84 (EPSG:4326), GeoJSON lon/lat order
- Hail size thresholds: `0.75", 1.00", 1.50", 2.00"` (0.75" is both the minimum cutoff and lowest threshold)
- Feature properties MUST include: `threshold`, `product`, `start_time`, `end_time`, `source_files`, `created_at`
- Handle missing files gracefully — log a warning, never crash
- No proprietary vendor data. Clean-room implementation using only public NOAA MRMS.

## Key Pitfalls

- **Units**: MRMS MESH may be in mm, not inches. Check metadata, convert if needed (1 inch = 25.4 mm).
- **GRIB2 decoding**: If `cfgrib` fails, try `backend_kwargs={'indexpath': ''}` or fall back to `pygrib`. Dockerfile must have `libeccodes-dev`.
- **Large grids**: MRMS CONUS is ~7000×3500 pixels. Clip to bbox early for performance.
- **Polygon validity**: Always `make_valid()` after polygonizing AND after simplifying.
- **File timestamps**: Parse from the MRMS filename, not S3 `LastModified`.
- **CORS**: Next.js dev server runs on a different port — enable CORS on the FastAPI app.

# Step 5 — Web Viewer (Next.js + Mapbox GL JS)

## Goal
Build a Next.js application in `web/` that displays hail swath polygons on an interactive map using Mapbox GL JS.

## Directory
```
web/
├── src/
│   └── app/
│       ├── page.tsx        # Main map page
│       ├── layout.tsx      # Root layout
│       └── globals.css     # Global styles
├── package.json
├── tsconfig.json
└── next.config.js
```

## Implementation Details

### Setup
```bash
cd web
npx create-next-app@latest . --typescript --tailwind --app
npm install mapbox-gl
```

### Map Page (`page.tsx`)
- Full-screen Mapbox GL JS map
- Tile source: `mapbox://styles/mapbox/satellite-streets-v12` (requires a Mapbox token in `web/.env.local`)
- On load, fetch `/swaths` from the FastAPI backend for the preselected test event
- API base URL should be configurable (env var or default to `http://localhost:8000`)

### Threshold Layers
Render each threshold as a separate GeoJSON layer with distinct colors:

| Threshold | Color | Label |
|-----------|-------|-------|
| 0.75"     | Yellow (`#FFD700`) | ≥ 0.75" |
| 1.00"     | Orange (`#FF8C00`) | ≥ 1.00" |
| 1.50"     | Red (`#FF0000`) | ≥ 1.50" |
| 2.00"     | Purple (`#800080`) | ≥ 2.00" |

- Polygons should be semi-transparent (fill-opacity ~0.4)
- Add outline strokes for clarity

### Legend
- Fixed-position legend overlay showing threshold → color mapping
- Simple HTML/CSS, no library needed

### Map Controls
- Zoom and pan controls
- Center on the test event area on load
- Optional: popup on polygon click showing properties (threshold, product, time window)

### API Integration
- Fetch from FastAPI backend: `http://localhost:8000/swaths?start_time=...&end_time=...`
- Preselect the test event time window (from Step 1)
- Handle loading state and errors gracefully

## Dependencies
- `next` (via create-next-app)
- `react`, `react-dom`
- `mapbox-gl`
- `typescript`, `tailwindcss` (via create-next-app)

## Depends On
- Step 1 (test event date for default query)
- Step 4 (API must be running to serve data)

## Verification
- `cd web && npm run dev` starts the Next.js dev server
- Map loads with tile basemap
- Polygons render with correct colors per threshold
- Legend is visible and accurate
- Clicking a polygon shows its properties (optional)

## Notes
- The FastAPI server must have CORS enabled (handled in Step 4)
- Keep it simple — single map page, no complex routing or state management
- Mapbox GL JS requires a free Mapbox token stored in `web/.env.local` as `NEXT_PUBLIC_MAPBOX_TOKEN`

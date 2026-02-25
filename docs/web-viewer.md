# Web Viewer

How the map in the browser works.

---

## Overview

The web viewer is a single-page Next.js app that displays hail swath polygons on a satellite map. It lives in the `web/` folder and runs on `http://localhost:3000`.

When you open it, it:
1. Shows a satellite map of the US
2. Calls the API to get hail polygon data for the test event (May 22, 2024)
3. Draws the polygons on the map, colored by hail size
4. Shows a sidebar with two tabs: Locations and Controls

---

## How to Run It

Make sure the API is running first:
```bash
docker compose up
```

Then start the web viewer:
```bash
cd web
npm install    # first time only
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## Map Layers

The map is built with layers stacked on top of each other, bottom to top:

```
Top:    City/town labels (white text, dark outline)
        State labels
        Highway lines + route numbers (toggle-able)
        ─────────────────────────────────
Middle: Hail polygons (colored by threshold)
        ─────────────────────────────────
Bottom: Satellite imagery (ESRI World Imagery)
```

The hail polygons sit between the satellite imagery and the labels. This way, you can see the terrain under the polygons AND read the city/road names on top.

### Basemap

We use **ESRI World Imagery** for the satellite background — it's free and doesn't need an API key.

### Road and City Labels

We use **OpenFreeMap** vector tiles for city names and highway labels. Vector means the text is rendered as crisp, styled shapes (not blurry images), with white/dark halos so they're readable over any background.

Roads are hidden by default. There's a "Show Roads" button in the top-left corner of the map to toggle major highways (interstates and US highways only — not every street).

---

## Sidebar

The sidebar on the left has two tabs: **Locations** and **Controls**.

### Header

Project name and the date of the hail event.

### Locations Tab

A scrollable list of hail locations. Each location is a cluster of nearby hail polygons grouped together.

**What each row shows:**
- A colored dot matching the severity (higher threshold = darker red)
- The location name (city, state) — resolved using OpenStreetMap's Nominatim reverse geocoding service
- The hail size thresholds detected at that location (e.g., `2", 1.5", 1", 0.75"`)
- The maximum threshold as a badge on the right

**How it works:**
- The list updates automatically as you pan and zoom the map — it only shows locations visible in the current viewport
- Click any row to fly to that location on the map
- Hover over a row to highlight it
- The count at the top shows how many locations are in view vs. total (e.g., "12 of 71 locations in view")

**Location names** are loaded in the background using the Nominatim API (free, no API key). While names are loading, coordinates are shown as a fallback (e.g., `33.05°N, 96.19°W`).

**Clustering:** Nearby polygons (within ~0.5 degrees / ~50km) are grouped into a single location. This prevents the list from being overwhelmed with hundreds of individual polygons. Locations are sorted by severity — the most severe hail locations appear first.

### Controls Tab

#### Threshold Checkboxes

One row per hail size threshold with a checkbox to toggle visibility on the map. Each row shows:
- A checkbox (checked = visible on map, unchecked = hidden)
- A colored dot matching the polygon color
- The threshold value (e.g., ">= 1.00"")

Unchecking a threshold hides all polygons of that size from the map.

#### Opacity Slider

A range slider (0%–100%) that controls how transparent the polygons are. Drag left to see more satellite imagery through the polygons. Drag right for more solid colors. Defaults to 50%.

### Footer

A reminder that this data is from NOAA MRMS and represents radar estimates, not confirmed damage.

---

## Polygon Colors

Each threshold has its own color so you can tell them apart on the map:

| Threshold | Color | Hex |
|-----------|-------|-----|
| >= 0.75" | Yellow-green | `#9E9D24` |
| >= 1.00" | Amber | `#F9A825` |
| >= 1.50" | Deep orange | `#E65100` |
| >= 2.00" | Dark red | `#BF360C` |

Larger thresholds are drawn first (bottom), smaller thresholds on top. This means if a 2.00" area is inside a 0.75" area, you'll see the red poking through the yellow-green.

---

## Clicking Polygons

Click any polygon on the map to see a popup with:
- The hail size threshold
- The radar product name
- The time window

---

## How It Talks to the API

The viewer makes one HTTP request when it loads:

```
GET http://localhost:8000/swaths?start_time=2024-05-22T20:00:00Z&end_time=2024-05-22T22:00:00Z
```

The API URL is configurable via the `NEXT_PUBLIC_API_URL` environment variable, but defaults to `http://localhost:8000`.

The response is a GeoJSON FeatureCollection. The viewer splits it by threshold value and creates a separate map layer for each threshold. This is what allows toggling individual thresholds on and off.

---

## Tech Stack

| Tool | What it does |
|------|-------------|
| **Next.js** | React framework that runs the web app |
| **TypeScript** | JavaScript with types (catches bugs at build time) |
| **Mapbox GL JS** | Renders the interactive map (requires a Mapbox token) |
| **Mapbox Satellite Streets** | Satellite imagery with road and label overlays |
| **Nominatim** | Reverse geocoding for location names (free, no API key) |

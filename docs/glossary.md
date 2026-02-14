# Glossary

Plain-English definitions of every technical term used in this project.

---

## Radar & Weather Terms

### MRMS (Multi-Radar Multi-Sensor)

A system run by NOAA (the US weather agency) that combines data from hundreds of radars across the country into a single, unified picture. Think of it like stitching together photos from many cameras into one panorama, but for weather radar.

### MESH (Maximum Estimated Size of Hail)

A radar-based guess of how big the hail is at each location, measured in inches. It's not someone on the ground measuring hailstones — it's the radar looking at how strong the storm echoes are and estimating "the hail here is probably about 1.5 inches in diameter."

Important: MESH is an **estimate**, not a measurement. It can be wrong. Sometimes it says there's hail where there isn't, and vice versa.

### Hail Exposure

An area where radar **estimated** hail of a certain size. This is NOT the same as confirmed damage. Just because radar says "1-inch hail was here" doesn't mean roofs were damaged. We use "exposure" to make this distinction clear.

### Swath

Imagine dragging a paintbrush across a map. The trail it leaves behind is a swath. In our case, a hail swath is the trail-shaped area that a hailstorm leaves behind as it moves across the ground over time. Storms move, so instead of a single circle, you get an elongated shape — that's the swath.

### Swath Polygon

A polygon is just a shape with straight edges (like drawing a shape by connecting dots). A swath polygon is the simplified outline of a hail swath drawn on a map. We take the radar's grid of hail estimates and draw a boundary around the areas that had hail above a certain size.

### Threshold

A cutoff value. When we say "threshold = 1.00 inch," we mean "show me everywhere the radar estimated hail of 1 inch or larger." The project uses four thresholds:

- **0.75"** — Small hail (about the size of a penny)
- **1.00"** — Quarter-sized hail
- **1.50"** — Golf ball-sized hail
- **2.00"** — Hen egg-sized hail

### Compositing

Combining multiple snapshots into one. The radar takes a new picture every 2 minutes. If you want to see the full hail swath from 8pm to 10pm, you need to combine all those snapshots together. We do this by keeping the **maximum** value at each location — if one snapshot says 1 inch and another says 2 inches at the same spot, we keep 2 inches.

---

## Data & File Terms

### GRIB2

A file format used by weather agencies to store gridded data (data arranged in a grid of rows and columns, like a spreadsheet but for maps). Think of it like a specialized image format where each pixel contains a hail size number instead of a color. We use a library called `cfgrib` to read these files.

### GeoJSON

A simple file format for storing geographic shapes (points, lines, polygons) as JSON. It's what web maps understand. Our entire pipeline converts radar data **into** GeoJSON so the map can display it.

Example of what a GeoJSON feature looks like:
```json
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[-97.5, 35.0], [-97.4, 35.0], [-97.4, 35.1], [-97.5, 35.1], [-97.5, 35.0]]]
  },
  "properties": {
    "threshold": 1.0,
    "product": "MESH_Max_60min"
  }
}
```

### S3 Bucket

Amazon's cloud storage service. NOAA stores MRMS radar files in a **public** S3 bucket (like a shared folder anyone can read from). We download files from `s3://noaa-mrms-pds/`. No account or API key needed.

### WGS84 / EPSG:4326

The coordinate system that uses latitude and longitude (the numbers you see in Google Maps). All our data uses this system. Longitude comes first in GeoJSON: `[longitude, latitude]` = `[-97.5, 35.0]`.

### Affine Transform

A math formula that converts between pixel positions (row 5, column 10) and real-world coordinates (longitude -97.5, latitude 35.0). Every radar grid file needs one so we know where each pixel is on Earth.

---

## Code & Architecture Terms

### Polygonize / Polygonization

The process of converting a grid (a 2D array of numbers) into shapes (polygons). Imagine a grid where some cells are "yes" (hail above threshold) and others are "no." Polygonization draws a boundary around all the "yes" cells and turns that boundary into a polygon shape.

### Binary Mask

A grid of true/false values. We create one by asking "is the hail size at this pixel >= the threshold?" Every pixel gets a yes (true) or no (false). This mask is what we then turn into polygons.

### Morphological Cleanup

After creating the binary mask, there might be tiny isolated pixels (noise) or small gaps in otherwise solid areas. Morphological cleanup smooths these out:
- **Closing** fills small gaps (like filling potholes in a road)
- **Opening** removes small isolated dots (like removing dust specks from a photo)

### Simplification

The raw polygons from the radar grid have very jagged edges (because the grid is made of tiny squares). Simplification smooths these edges so the shapes look nicer and the files are smaller. We use a "tolerance" value — higher tolerance = smoother but less accurate shapes.

### make_valid()

Sometimes the math that creates polygons produces shapes that are technically broken (like a figure-8 where the outline crosses itself). `make_valid()` fixes these broken shapes so they work correctly in maps and calculations.

### Feature / FeatureCollection

GeoJSON terms. A **Feature** is one shape with its data (one hail polygon with its threshold, time, etc.). A **FeatureCollection** is a list of Features — our API returns one FeatureCollection containing all the hail polygons for all thresholds.

### CORS (Cross-Origin Resource Sharing)

A browser security rule. The API runs on port 8000 and the web viewer runs on port 3000. By default, the browser blocks the web page from talking to a different port. CORS is a setting on the API that says "it's OK, let the web page talk to me."

---

## Infrastructure Terms

### FastAPI

A Python web framework we use to build the API server. It handles incoming requests (like "give me hail polygons for May 22"), runs the data pipeline, and sends back the results as JSON.

### MapLibre GL JS

A JavaScript library for displaying interactive maps in the browser. It handles the satellite imagery, renders our hail polygons on top, and lets users zoom/pan/click.

### Docker / Docker Compose

Docker packages our entire application (Python code + system libraries + dependencies) into a single container that works the same on any computer. `docker compose up` starts everything with one command. This avoids "it works on my machine" problems.

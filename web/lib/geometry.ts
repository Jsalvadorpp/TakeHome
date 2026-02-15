import maplibregl from "maplibre-gl";

/**
 * Compute the centroid of a GeoJSON geometry by averaging all coordinates.
 *
 * Walks through nested coordinate arrays and calculates the average
 * longitude and latitude.
 *
 * Example:
 *   Input: { type: "Polygon", coordinates: [[[-95, 35], [-95, 36], [-94, 36]]] }
 *   Output: [-94.67, 35.33]
 */
export function getCentroid(geometry: any): [number, number] {
  let sumLng = 0;
  let sumLat = 0;
  let count = 0;

  function walk(coords: any) {
    if (typeof coords[0] === "number") {
      sumLng += coords[0];
      sumLat += coords[1];
      count++;
    } else {
      for (const c of coords) walk(c);
    }
  }

  walk(geometry.coordinates);
  return count > 0 ? [sumLng / count, sumLat / count] : [0, 0];
}

/**
 * Compute the bounding box of a GeoJSON geometry.
 *
 * Returns a MapLibre LngLatBounds object containing all coordinates.
 */
export function getGeometryBounds(geometry: any): maplibregl.LngLatBounds {
  const bounds = new maplibregl.LngLatBounds();
  addCoordsToBounds(geometry.coordinates, bounds);
  return bounds;
}

/**
 * Recursively add all coordinates from a GeoJSON geometry to a bounds object.
 *
 * Handles nested coordinate arrays (Polygon, MultiPolygon, etc.)
 */
export function addCoordsToBounds(
  coords: any,
  bounds: maplibregl.LngLatBounds
): void {
  if (typeof coords[0] === "number") {
    bounds.extend(coords as [number, number]);
  } else {
    for (const child of coords) {
      addCoordsToBounds(child, bounds);
    }
  }
}

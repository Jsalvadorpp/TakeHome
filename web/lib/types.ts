import type maplibregl from "maplibre-gl";

/**
 * A hail location represents a cluster of nearby hail polygons grouped together.
 *
 * Used for displaying locations in the sidebar list.
 */
export interface HailLocation {
  id: number;
  lat: number;
  lng: number;
  maxThreshold: number;
  thresholds: number[];
  bounds: maplibregl.LngLatBounds;
}

import type maplibregl from "maplibre-gl";

/**
 * MapLibre style configuration with satellite imagery and vector labels.
 *
 * Uses free, public tile sources - no API keys required:
 * - Satellite imagery: ArcGIS World Imagery
 * - Vector tiles: OpenFreeMap
 */
export const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution:
        "&copy; Esri, Maxar, Earthstar Geographics &middot; &copy; OpenMapTiles &copy; OpenStreetMap",
    },
    openmaptiles: {
      type: "vector",
      url: "https://tiles.openfreemap.org/planet",
    },
  },
  layers: [
    { id: "satellite", type: "raster", source: "satellite" },
    {
      id: "highway-casing",
      type: "line",
      source: "openmaptiles",
      "source-layer": "transportation",
      filter: ["in", "class", "motorway", "trunk"],
      paint: {
        "line-color": "rgba(0,0,0,0.4)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 1.5, 10, 4, 14, 8],
      },
      layout: { "line-cap": "round", "line-join": "round", "visibility": "none" },
    },
    {
      id: "highway-fill",
      type: "line",
      source: "openmaptiles",
      "source-layer": "transportation",
      filter: ["in", "class", "motorway", "trunk"],
      paint: {
        "line-color": "rgba(255,255,255,0.8)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.8, 10, 2.5, 14, 5],
      },
      layout: { "line-cap": "round", "line-join": "round", "visibility": "none" },
    },
    {
      id: "highway-label",
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "transportation_name",
      filter: ["in", "class", "motorway", "trunk"],
      layout: {
        "symbol-placement": "line",
        "text-field": "{ref}",
        "text-font": ["Open Sans Bold"],
        "text-size": 11,
        "text-rotation-alignment": "map",
        "symbol-spacing": 400,
        "visibility": "none",
      },
      paint: {
        "text-color": "#333",
        "text-halo-color": "rgba(255,255,255,0.95)",
        "text-halo-width": 2,
      },
    },
    {
      id: "place-label",
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "place",
      filter: ["in", "class", "city", "town", "village", "suburb"],
      layout: {
        "text-field": "{name}",
        "text-font": ["Open Sans Bold"],
        "text-size": ["interpolate", ["linear"], ["zoom"],
          5, ["match", ["get", "class"], "city", 14, 10],
          10, ["match", ["get", "class"], "city", 18, "town", 14, 12],
          14, ["match", ["get", "class"], "city", 22, "town", 16, 14],
        ],
        "text-anchor": "center",
        "text-max-width": 8,
      },
      paint: {
        "text-color": "#ffffff",
        "text-halo-color": "rgba(0,0,0,0.7)",
        "text-halo-width": 2,
      },
    },
    {
      id: "boundary-label",
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "place",
      filter: ["==", "class", "state"],
      minzoom: 4,
      maxzoom: 8,
      layout: {
        "text-field": "{name}",
        "text-font": ["Open Sans Bold"],
        "text-size": 12,
        "text-transform": "uppercase",
        "text-letter-spacing": 0.15,
      },
      paint: {
        "text-color": "rgba(255,255,255,0.8)",
        "text-halo-color": "rgba(0,0,0,0.6)",
        "text-halo-width": 1.5,
      },
    },
  ],
};

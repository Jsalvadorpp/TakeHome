"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Test event: May 22, 2024 severe hail outbreak
const DEFAULT_START = "2024-05-22T20:00:00Z";
const DEFAULT_END = "2024-05-22T22:00:00Z";

// Satellite basemap + vector roads/labels for readability (all free, no API keys)
const SATELLITE_STYLE: maplibregl.StyleSpecification = {
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
    // Satellite imagery base
    { id: "satellite", type: "raster", source: "satellite" },

    // --- Vector road/label layers render on top of swaths ---

    // Major highway casings (dark outline behind road fill)
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
    // Major highway fills (white/light)
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
    // Highway route numbers
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
    // City / town / village labels
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
    // State / county boundaries
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

// Threshold colors — earthy warm gradient (yellow-green → orange → dark red-brown)
// Matches typical hail swath map styling. Largest first so smaller render on top.
const THRESHOLDS = [
  { value: 2.0, color: "#BF360C", label: '2.00"', opacity: 0.7 },
  { value: 1.5, color: "#E65100", label: '1.50"', opacity: 0.6 },
  { value: 1.0, color: "#F9A825", label: '1.00"', opacity: 0.5 },
  { value: 0.75, color: "#9E9D24", label: '0.75"', opacity: 0.4 },
];

interface FeatureCounts {
  [key: number]: number;
}

export default function Home() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [featureCounts, setFeatureCounts] = useState<FeatureCounts>({});
  const [totalFeatures, setTotalFeatures] = useState(0);
  const [roadsVisible, setRoadsVisible] = useState(false);
  const [opacity, setOpacity] = useState(0.5);
  const [hiddenThresholds, setHiddenThresholds] = useState<Set<number>>(new Set());

  const ROAD_LAYER_IDS = ["highway-casing", "highway-fill", "highway-label"];

  function toggleRoads() {
    const map = mapRef.current;
    if (!map) return;

    const newVisible = !roadsVisible;
    const visibility = newVisible ? "visible" : "none";
    for (const id of ROAD_LAYER_IDS) {
      if (map.getLayer(id)) {
        map.setLayoutProperty(id, "visibility", visibility);
      }
    }
    setRoadsVisible(newVisible);
  }

  function toggleThreshold(value: number) {
    const map = mapRef.current;
    if (!map) return;

    const layerId = `swath-${value}-fill`;
    if (!map.getLayer(layerId)) return;

    const newHidden = new Set(hiddenThresholds);
    if (newHidden.has(value)) {
      newHidden.delete(value);
      map.setLayoutProperty(layerId, "visibility", "visible");
    } else {
      newHidden.add(value);
      map.setLayoutProperty(layerId, "visibility", "none");
    }
    setHiddenThresholds(newHidden);
  }

  function handleOpacityChange(newOpacity: number) {
    setOpacity(newOpacity);
    const map = mapRef.current;
    if (!map) return;

    for (const t of THRESHOLDS) {
      const layerId = `swath-${t.value}-fill`;
      if (map.getLayer(layerId)) {
        map.setPaintProperty(layerId, "fill-opacity", newOpacity);
      }
    }
  }

  useEffect(() => {
    if (!mapContainer.current) return;

    const newMap = new maplibregl.Map({
      container: mapContainer.current,
      style: SATELLITE_STYLE,
      center: [-98, 38],
      zoom: 5,
    });

    newMap.addControl(new maplibregl.NavigationControl(), "top-right");

    newMap.on("load", () => {
      mapRef.current = newMap;
      fetchSwaths(newMap);
    });

    return () => {
      newMap.remove();
    };
  }, []);

  async function fetchSwaths(mapInstance: maplibregl.Map) {
    try {
      setLoading(true);
      setError(null);

      const url = `${API_BASE}/swaths?start_time=${DEFAULT_START}&end_time=${DEFAULT_END}`;
      const response = await fetch(url);

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || `API returned ${response.status}`);
      }

      const geojson = await response.json();
      addLayers(mapInstance, geojson);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load swath data"
      );
    } finally {
      setLoading(false);
    }
  }

  function addLayers(mapInstance: maplibregl.Map, geojson: any) {
    const counts: FeatureCounts = {};

    for (const threshold of THRESHOLDS) {
      const layerId = `swath-${threshold.value}`;

      const filtered = {
        ...geojson,
        features: geojson.features.filter(
          (f: any) => f.properties.threshold === threshold.value
        ),
      };

      counts[threshold.value] = filtered.features.length;
      if (filtered.features.length === 0) continue;

      mapInstance.addSource(layerId, {
        type: "geojson",
        data: filtered,
      });

      // Fill only — no outline strokes for a smooth, blended look
      // Insert below vector roads so labels stay readable
      mapInstance.addLayer(
        {
          id: `${layerId}-fill`,
          type: "fill",
          source: layerId,
          paint: {
            "fill-color": threshold.color,
            "fill-opacity": opacity,
          },
        },
        "highway-casing"
      );

      // Popup on click
      mapInstance.on("click", `${layerId}-fill`, (e) => {
        if (!e.features || e.features.length === 0) return;
        const props = e.features[0].properties;
        new maplibregl.Popup()
          .setLngLat(e.lngLat)
          .setHTML(
            `<div style="font-size:13px;line-height:1.6">` +
              `<div style="font-weight:600;margin-bottom:4px">Hail Exposure</div>` +
              `<div>MESH: <strong>${props.threshold}"</strong></div>` +
              `<div>Product: ${props.product}</div>` +
              `<div>Window: ${formatTime(props.start_time)} – ${formatTime(props.end_time)}</div>` +
              `</div>`
          )
          .addTo(mapInstance);
      });

      mapInstance.on("mouseenter", `${layerId}-fill`, () => {
        mapInstance.getCanvas().style.cursor = "pointer";
      });
      mapInstance.on("mouseleave", `${layerId}-fill`, () => {
        mapInstance.getCanvas().style.cursor = "";
      });
    }

    setFeatureCounts(counts);
    setTotalFeatures(geojson.features.length);

    // Zoom to fit
    if (geojson.features.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      for (const feature of geojson.features) {
        addCoordsToBounds(feature.geometry.coordinates, bounds);
      }
      mapInstance.fitBounds(bounds, {
        padding: { top: 50, bottom: 50, left: 330, right: 50 },
      });
    }
  }

  return (
    <div style={{ width: "100vw", height: "100vh", display: "flex" }}>
      {/* Sidebar — white background, matching reference */}
      <div
        style={{
          width: 300,
          minWidth: 300,
          height: "100%",
          background: "#ffffff",
          color: "#333",
          display: "flex",
          flexDirection: "column",
          overflow: "auto",
          borderRight: "1px solid #e0e0e0",
          fontFamily: "system-ui, -apple-system, sans-serif",
        }}
      >
        {/* Header */}
        <div style={{ padding: "16px 16px 12px", borderBottom: "1px solid #eee" }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#222" }}>
            Hail Exposure Map
          </div>
          <div style={{ fontSize: 12, color: "#888", marginTop: 2 }}>
            MRMS MESH Swaths
          </div>
        </div>

        {/* Weather History label */}
        <div
          style={{
            padding: "14px 16px 8px",
            fontSize: 13,
            fontWeight: 600,
            color: "#333",
          }}
        >
          Weather History
        </div>

        {/* Events header */}
        <div
          style={{
            padding: "4px 16px 12px",
            borderBottom: "1px solid #eee",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: "#222" }}>
            Events At Location
          </div>
          <div style={{ fontSize: 12, color: "#999", marginTop: 2 }}>
            {loading
              ? "Loading..."
              : error
                ? "Error loading data"
                : `${totalFeatures} detections found`}
          </div>
        </div>

        {/* Threshold toggles */}
        <div style={{ flex: 1, overflow: "auto" }}>
          {error && (
            <div
              style={{
                margin: "12px 16px",
                padding: "10px 12px",
                background: "#FEE2E2",
                color: "#DC2626",
                borderRadius: 6,
                fontSize: 13,
              }}
            >
              {error}
            </div>
          )}

          {!loading &&
            !error &&
            [...THRESHOLDS].reverse().map((t) => {
              const isHidden = hiddenThresholds.has(t.value);
              return (
                <div
                  key={t.value}
                  onClick={() => toggleThreshold(t.value)}
                  style={{
                    ...eventCardStyle,
                    cursor: "pointer",
                    opacity: isHidden ? 0.4 : 1,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div
                        style={{
                          width: 14,
                          height: 14,
                          borderRadius: "50%",
                          background: isHidden ? "#ccc" : t.color,
                        }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>
                        &ge; {t.label}
                      </span>
                    </div>
                    <span style={{ fontSize: 12, color: "#999" }}>
                      {featureCounts[t.value] ?? 0}
                    </span>
                  </div>
                </div>
              );
            })}

          {/* Opacity slider */}
          {!loading && !error && (
            <div style={{ padding: "16px 16px 12px" }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 12,
                  color: "#666",
                  marginBottom: 6,
                }}
              >
                <span>Opacity</span>
                <span>{Math.round(opacity * 100)}%</span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={Math.round(opacity * 100)}
                onChange={(e) => handleOpacityChange(Number(e.target.value) / 100)}
                style={{ width: "100%", cursor: "pointer" }}
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "10px 16px",
            borderTop: "1px solid #eee",
            fontSize: 10,
            color: "#bbb",
          }}
        >
          Data: NOAA MRMS (public) &middot; Not confirmed damage
        </div>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: "relative" }}>
        <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />

        {/* Roads toggle button */}
        <button
          onClick={toggleRoads}
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            background: roadsVisible ? "#43A047" : "rgba(255,255,255,0.9)",
            color: roadsVisible ? "#fff" : "#333",
            border: "none",
            borderRadius: 6,
            padding: "8px 14px",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
          }}
        >
          {roadsVisible ? "Hide Roads" : "Show Roads"}
        </button>

        {/* Loading overlay on map */}
        {loading && (
          <div
            style={{
              position: "absolute",
              top: 12,
              left: "50%",
              transform: "translateX(-50%)",
              background: "rgba(255,255,255,0.95)",
              color: "#333",
              padding: "8px 20px",
              borderRadius: 8,
              fontSize: 13,
              boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
            }}
          >
            Loading swath data...
          </div>
        )}
      </div>
    </div>
  );
}

const eventCardStyle: React.CSSProperties = {
  margin: "0 12px",
  padding: "12px",
  borderBottom: "1px solid #f0f0f0",
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC",
    });
  } catch {
    return iso;
  }
}

function addCoordsToBounds(
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

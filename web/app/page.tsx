"use client";

import { useEffect, useRef, useState, useCallback } from "react";
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

const THRESHOLDS = [
  { value: 2.0, color: "#BF360C", label: '2.00"', opacity: 0.7 },
  { value: 1.5, color: "#E65100", label: '1.50"', opacity: 0.6 },
  { value: 1.0, color: "#F9A825", label: '1.00"', opacity: 0.5 },
  { value: 0.75, color: "#9E9D24", label: '0.75"', opacity: 0.4 },
];

const THRESHOLD_MAP: Record<number, typeof THRESHOLDS[0]> = {};
for (const t of THRESHOLDS) THRESHOLD_MAP[t.value] = t;

// A hail location = a cluster of nearby polygons grouped together
interface HailLocation {
  id: number;
  lat: number;
  lng: number;
  maxThreshold: number;
  thresholds: number[];
  bounds: maplibregl.LngLatBounds;
}

// Compute centroid of a GeoJSON geometry by averaging all coordinates
function getCentroid(geometry: any): [number, number] {
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

// Compute bounds of a GeoJSON geometry
function getGeometryBounds(geometry: any): maplibregl.LngLatBounds {
  const bounds = new maplibregl.LngLatBounds();
  addCoordsToBounds(geometry.coordinates, bounds);
  return bounds;
}

// Group features into locations by clustering nearby centroids
function clusterFeatures(features: any[]): HailLocation[] {
  // Sort by threshold descending so highest severity comes first
  const sorted = [...features].sort(
    (a, b) => b.properties.threshold - a.properties.threshold
  );

  const locations: HailLocation[] = [];
  const assigned = new Set<number>();

  // Simple distance-based clustering: ~0.5 degrees (~50km)
  const CLUSTER_DISTANCE = 0.5;

  for (let i = 0; i < sorted.length; i++) {
    if (assigned.has(i)) continue;

    const centroid = getCentroid(sorted[i].geometry);
    const bounds = getGeometryBounds(sorted[i].geometry);
    const thresholds = new Set<number>([sorted[i].properties.threshold]);

    // Find nearby features and merge into this cluster
    for (let j = i + 1; j < sorted.length; j++) {
      if (assigned.has(j)) continue;
      const other = getCentroid(sorted[j].geometry);
      const dist = Math.sqrt(
        (centroid[0] - other[0]) ** 2 + (centroid[1] - other[1]) ** 2
      );
      if (dist < CLUSTER_DISTANCE) {
        assigned.add(j);
        thresholds.add(sorted[j].properties.threshold);
        const otherBounds = getGeometryBounds(sorted[j].geometry);
        bounds.extend(otherBounds.getSouthWest());
        bounds.extend(otherBounds.getNorthEast());
      }
    }

    assigned.add(i);
    locations.push({
      id: locations.length,
      lng: centroid[0],
      lat: centroid[1],
      maxThreshold: sorted[i].properties.threshold,
      thresholds: Array.from(thresholds).sort((a, b) => b - a),
      bounds,
    });
  }

  // Sort by max threshold descending
  locations.sort((a, b) => b.maxThreshold - a.maxThreshold);
  return locations;
}

export default function Home() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [roadsVisible, setRoadsVisible] = useState(false);
  const [opacity, setOpacity] = useState(0.5);
  const [hiddenThresholds, setHiddenThresholds] = useState<Set<number>>(new Set());
  const [allLocations, setAllLocations] = useState<HailLocation[]>([]);
  const [visibleLocations, setVisibleLocations] = useState<HailLocation[]>([]);
  const [sidebarTab, setSidebarTab] = useState<"controls" | "locations">("locations");
  const [locationNames, setLocationNames] = useState<Record<number, string>>({});

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

  function flyToLocation(location: HailLocation) {
    const map = mapRef.current;
    if (!map) return;
    map.fitBounds(location.bounds, {
      padding: { top: 60, bottom: 60, left: 340, right: 60 },
      maxZoom: 11,
    });
  }

  // Update visible locations when the map moves
  const updateVisibleLocations = useCallback(() => {
    const map = mapRef.current;
    if (!map || allLocations.length === 0) return;

    const bounds = map.getBounds();
    const visible = allLocations.filter((loc) =>
      bounds.contains(new maplibregl.LngLat(loc.lng, loc.lat))
    );
    setVisibleLocations(visible);
  }, [allLocations]);

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

  // Reverse geocode locations to get city/state names
  useEffect(() => {
    if (allLocations.length === 0) return;

    let cancelled = false;

    async function geocodeAll() {
      for (const loc of allLocations) {
        if (cancelled) break;
        try {
          const resp = await fetch(
            `https://nominatim.openstreetmap.org/reverse?lat=${loc.lat}&lon=${loc.lng}&format=json&zoom=10&addressdetails=1`
          );
          if (!resp.ok) continue;
          const data = await resp.json();
          const addr = data.address || {};
          const city =
            addr.city || addr.town || addr.village || addr.hamlet || addr.county || "";
          const state = addr.state || "";
          const name = city && state ? `${city}, ${state}` : city || state || "";
          if (name && !cancelled) {
            setLocationNames((prev) => ({ ...prev, [loc.id]: name }));
          }
        } catch {
          // Keep coordinate fallback
        }
        // Nominatim rate limit: 1 request per second
        await new Promise((r) => setTimeout(r, 1100));
      }
    }

    geocodeAll();
    return () => {
      cancelled = true;
    };
  }, [allLocations]);

  // Listen for map move events to update visible locations
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    map.on("moveend", updateVisibleLocations);
    // Run once immediately
    updateVisibleLocations();

    return () => {
      map.off("moveend", updateVisibleLocations);
    };
  }, [updateVisibleLocations]);

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
    for (const threshold of THRESHOLDS) {
      const layerId = `swath-${threshold.value}`;

      const filtered = {
        ...geojson,
        features: geojson.features.filter(
          (f: any) => f.properties.threshold === threshold.value
        ),
      };

      if (filtered.features.length === 0) continue;

      mapInstance.addSource(layerId, {
        type: "geojson",
        data: filtered,
      });

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

    // Build location clusters from all features
    const locations = clusterFeatures(geojson.features);
    setAllLocations(locations);

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
      {/* Sidebar */}
      <div
        style={{
          width: 300,
          minWidth: 300,
          height: "100%",
          background: "#ffffff",
          color: "#333",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
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
            MRMS MESH Swaths &middot; May 22, 2024
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid #eee" }}>
          <button
            onClick={() => setSidebarTab("locations")}
            style={{
              ...tabStyle,
              borderBottom: sidebarTab === "locations" ? "2px solid #43A047" : "2px solid transparent",
              color: sidebarTab === "locations" ? "#222" : "#999",
            }}
          >
            Locations
          </button>
          <button
            onClick={() => setSidebarTab("controls")}
            style={{
              ...tabStyle,
              borderBottom: sidebarTab === "controls" ? "2px solid #43A047" : "2px solid transparent",
              color: sidebarTab === "controls" ? "#222" : "#999",
            }}
          >
            Controls
          </button>
        </div>

        {/* Tab content */}
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

          {/* Locations tab */}
          {sidebarTab === "locations" && !loading && !error && (
            <>
              <div
                style={{
                  padding: "10px 16px",
                  fontSize: 12,
                  color: "#888",
                  borderBottom: "1px solid #f0f0f0",
                }}
              >
                {visibleLocations.length} of {allLocations.length} locations in view
              </div>

              {visibleLocations.length === 0 && (
                <div style={{ padding: "24px 16px", fontSize: 13, color: "#999", textAlign: "center" }}>
                  No hail locations in the current view. Zoom out or pan the map.
                </div>
              )}

              {visibleLocations.map((loc) => {
                const t = THRESHOLD_MAP[loc.maxThreshold];
                return (
                  <div
                    key={loc.id}
                    onClick={() => flyToLocation(loc)}
                    style={{
                      padding: "10px 16px",
                      borderBottom: "1px solid #f0f0f0",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.background = "#f7f7f7";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background = "";
                    }}
                  >
                    {/* Severity dot */}
                    <div
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        background: t?.color || "#999",
                        flexShrink: 0,
                      }}
                    />

                    {/* Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>
                        {locationNames[loc.id] || `${loc.lat.toFixed(2)}°N, ${Math.abs(loc.lng).toFixed(2)}°W`}
                      </div>
                      <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
                        {loc.thresholds.map((th) => `${th}"`).join(", ")}
                      </div>
                    </div>

                    {/* Max threshold badge */}
                    <div
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: t?.color || "#999",
                        flexShrink: 0,
                      }}
                    >
                      {loc.maxThreshold}"
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* Controls tab */}
          {sidebarTab === "controls" && !loading && !error && (
            <>
              {/* Threshold toggles */}
              <div style={{ padding: "8px 0" }}>
                <div
                  style={{
                    padding: "8px 16px 4px",
                    fontSize: 11,
                    color: "#888",
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  Thresholds
                </div>
                {[...THRESHOLDS].reverse().map((t) => {
                  const isHidden = hiddenThresholds.has(t.value);
                  return (
                    <label
                      key={t.value}
                      style={{
                        padding: "10px 16px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={!isHidden}
                        onChange={() => toggleThreshold(t.value)}
                        style={{
                          width: 16,
                          height: 16,
                          accentColor: t.color,
                          cursor: "pointer",
                          flexShrink: 0,
                        }}
                      />
                      <div
                        style={{
                          width: 14,
                          height: 14,
                          borderRadius: "50%",
                          background: isHidden ? "#ccc" : t.color,
                          flexShrink: 0,
                        }}
                      />
                      <span style={{ fontSize: 13, fontWeight: 600, color: isHidden ? "#999" : "#222" }}>
                        &ge; {t.label}
                      </span>
                    </label>
                  );
                })}
              </div>

              {/* Opacity slider */}
              <div style={{ padding: "12px 16px", borderTop: "1px solid #f0f0f0" }}>
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
            </>
          )}

          {loading && (
            <div style={{ padding: "24px 16px", fontSize: 13, color: "#999", textAlign: "center" }}>
              Loading hail data...
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

const tabStyle: React.CSSProperties = {
  flex: 1,
  background: "none",
  border: "none",
  padding: "10px 0",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
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

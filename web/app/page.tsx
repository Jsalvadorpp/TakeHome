"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import { SATELLITE_STYLE } from "@/lib/map-style";
import {
  DEFAULT_START,
  DEFAULT_END,
  THRESHOLDS,
  THRESHOLD_MAP,
  ROAD_LAYER_IDS,
} from "@/lib/constants";
import type { HailLocation } from "@/lib/types";
import { addCoordsToBounds } from "@/lib/geometry";
import { clusterFeatures } from "@/lib/clustering";
import { formatTime } from "@/lib/formatting";
import { reverseGeocode } from "@/lib/geocoding";
import { fetchSwathsData } from "@/lib/api";

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

        const name = await reverseGeocode(loc.lat, loc.lng);
        if (name && !cancelled) {
          setLocationNames((prev) => ({ ...prev, [loc.id]: name }));
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

      const geojson = await fetchSwathsData(DEFAULT_START, DEFAULT_END);
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

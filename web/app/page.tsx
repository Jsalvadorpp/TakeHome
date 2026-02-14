"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Test event: May 22, 2024 severe hail outbreak
const DEFAULT_START = "2024-05-22T20:00:00Z";
const DEFAULT_END = "2024-05-22T22:00:00Z";

// Threshold colors: largest first so smaller thresholds render on top
const THRESHOLDS = [
  { value: 2.0, color: "#800080", label: '≥ 2.00"' },
  { value: 1.5, color: "#FF0000", label: '≥ 1.50"' },
  { value: 1.0, color: "#FF8C00", label: '≥ 1.00"' },
  { value: 0.75, color: "#FFD700", label: '≥ 0.75"' },
];

export default function Home() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!mapContainer.current) return;

    const newMap = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
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
    for (const threshold of THRESHOLDS) {
      const layerId = `swath-${threshold.value}`;

      // Filter features for this threshold
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

      mapInstance.addLayer({
        id: `${layerId}-fill`,
        type: "fill",
        source: layerId,
        paint: {
          "fill-color": threshold.color,
          "fill-opacity": 0.4,
        },
      });

      mapInstance.addLayer({
        id: `${layerId}-outline`,
        type: "line",
        source: layerId,
        paint: {
          "line-color": threshold.color,
          "line-width": 1,
        },
      });

      // Popup on click
      mapInstance.on("click", `${layerId}-fill`, (e) => {
        if (!e.features || e.features.length === 0) return;
        const props = e.features[0].properties;
        new maplibregl.Popup()
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>Threshold:</strong> ${props.threshold}"<br/>` +
              `<strong>Product:</strong> ${props.product}<br/>` +
              `<strong>Time:</strong> ${props.start_time} – ${props.end_time}`
          )
          .addTo(mapInstance);
      });

      // Pointer cursor on hover
      mapInstance.on("mouseenter", `${layerId}-fill`, () => {
        mapInstance.getCanvas().style.cursor = "pointer";
      });
      mapInstance.on("mouseleave", `${layerId}-fill`, () => {
        mapInstance.getCanvas().style.cursor = "";
      });
    }

    // Zoom to fit the data
    if (geojson.features.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      for (const feature of geojson.features) {
        addCoordsToBounds(feature.geometry.coordinates, bounds);
      }
      mapInstance.fitBounds(bounds, { padding: 50 });
    }
  }

  return (
    <div style={{ width: "100vw", height: "100vh", position: "relative" }}>
      <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />

      {/* Legend */}
      <div
        style={{
          position: "absolute",
          bottom: 30,
          left: 10,
          background: "white",
          padding: "12px 16px",
          borderRadius: 8,
          boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
          fontSize: 14,
        }}
      >
        <div style={{ fontWeight: "bold", marginBottom: 8 }}>
          Hail Size (MESH)
        </div>
        {[...THRESHOLDS].reverse().map((t) => (
          <div
            key={t.value}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 4,
            }}
          >
            <div
              style={{
                width: 16,
                height: 16,
                backgroundColor: t.color,
                opacity: 0.7,
                borderRadius: 2,
                border: `1px solid ${t.color}`,
              }}
            />
            <span>{t.label}</span>
          </div>
        ))}
      </div>

      {/* Loading overlay */}
      {loading && (
        <div
          style={{
            position: "absolute",
            top: 10,
            left: "50%",
            transform: "translateX(-50%)",
            background: "white",
            padding: "8px 16px",
            borderRadius: 8,
            boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
          }}
        >
          Loading swath data...
        </div>
      )}

      {/* Error overlay */}
      {error && (
        <div
          style={{
            position: "absolute",
            top: 10,
            left: "50%",
            transform: "translateX(-50%)",
            background: "#fee2e2",
            color: "#dc2626",
            padding: "8px 16px",
            borderRadius: 8,
            boxShadow: "0 2px 6px rgba(0,0,0,0.2)",
          }}
        >
          Error: {error}
        </div>
      )}
    </div>
  );
}

// Helper to recursively add coordinates to bounds
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

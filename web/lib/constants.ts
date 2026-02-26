/**
 * Application constants and configuration values.
 *
 * These are shared across the application and define default values,
 * thresholds, and UI configuration.
 */

// API configuration
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Hail size thresholds with display properties.
//
// Color ramp — two zones:
//   0.50–1.75": warm ramp (cream → yellow → orange → red-orange → bright red)
//   2.00–2.75": #CC1800 family, lighter at 2.00" and progressively darker up to 2.75" (maroon)
//
// Sorted highest→lowest so larger swaths render underneath smaller ones on the map.
// strokeColor is a darker version of color used to outline polygon edges.
export const THRESHOLDS = [
  { value: 2.75, color: "#841000", strokeColor: "#570b00", label: '2.75"', opacity: 0.96 },
  { value: 2.50, color: "#A81300", strokeColor: "#6e0d00", label: '2.50"', opacity: 0.93 },
  { value: 2.25, color: "#CC1800", strokeColor: "#880e00", label: '2.25"', opacity: 0.90 },
  { value: 2.00, color: "#E83A1A", strokeColor: "#9b2712", label: '2.00"', opacity: 0.86 },
  { value: 1.75, color: "#FF2200", strokeColor: "#bf1800", label: '1.75"', opacity: 0.80 },
  { value: 1.50, color: "#FF5500", strokeColor: "#c03500", label: '1.50"', opacity: 0.72 },
  { value: 1.25, color: "#FF7A00", strokeColor: "#bf5800", label: '1.25"', opacity: 0.63 },
  { value: 1.00, color: "#FFA500", strokeColor: "#c07000", label: '1.00"', opacity: 0.55 },
  { value: 0.75, color: "#FFE04B", strokeColor: "#c0a000", label: '0.75"', opacity: 0.45 },
  { value: 0.50, color: "#FFFACD", strokeColor: "#c8b860", label: '0.50"', opacity: 0.35 },
];

// Map threshold values to their config objects for O(1) lookup
export const THRESHOLD_MAP: Record<number, typeof THRESHOLDS[0]> = {};
for (const t of THRESHOLDS) THRESHOLD_MAP[t.value] = t;


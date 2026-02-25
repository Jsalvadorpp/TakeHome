/**
 * Application constants and configuration values.
 *
 * These are shared across the application and define default values,
 * thresholds, and UI configuration.
 */

// API configuration
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Hail size thresholds with display properties.
// Colors follow the standard warm weather-radar ramp: cream → yellow → amber → orange → red.
// strokeColor is a darker version of color used to outline polygon edges.
export const THRESHOLDS = [
  { value: 2.0,  color: "#CC1800", strokeColor: "#880e00", label: '2.00"', opacity: 0.75 },
  { value: 1.5,  color: "#FF5500", strokeColor: "#c03500", label: '1.50"', opacity: 0.65 },
  { value: 1.0,  color: "#FFA500", strokeColor: "#c07000", label: '1.00"', opacity: 0.55 },
  { value: 0.75, color: "#FFE04B", strokeColor: "#c0a000", label: '0.75"', opacity: 0.45 },
  { value: 0.50, color: "#FFFACD", strokeColor: "#c8b860", label: '0.50"', opacity: 0.35 },
];

// Map threshold values to their config objects for O(1) lookup
export const THRESHOLD_MAP: Record<number, typeof THRESHOLDS[0]> = {};
for (const t of THRESHOLDS) THRESHOLD_MAP[t.value] = t;


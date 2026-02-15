/**
 * Application constants and configuration values.
 *
 * These are shared across the application and define default values,
 * thresholds, and UI configuration.
 */

// API configuration
export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Default time window for the test event (May 22, 2024 severe hail outbreak)
export const DEFAULT_START = "2024-05-22T20:00:00Z";
export const DEFAULT_END = "2024-05-22T22:00:00Z";

// Hail size thresholds with display properties
export const THRESHOLDS = [
  { value: 2.0, color: "#BF360C", label: '2.00"', opacity: 0.7 },
  { value: 1.5, color: "#E65100", label: '1.50"', opacity: 0.6 },
  { value: 1.0, color: "#F9A825", label: '1.00"', opacity: 0.5 },
  { value: 0.75, color: "#9E9D24", label: '0.75"', opacity: 0.4 },
];

// Map threshold values to their config objects for O(1) lookup
export const THRESHOLD_MAP: Record<number, typeof THRESHOLDS[0]> = {};
for (const t of THRESHOLDS) THRESHOLD_MAP[t.value] = t;

// Map layer IDs for roads overlay
export const ROAD_LAYER_IDS = ["highway-casing", "highway-fill", "highway-label"];

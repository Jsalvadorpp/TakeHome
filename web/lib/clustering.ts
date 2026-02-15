import type { HailLocation } from "./types";
import { getCentroid, getGeometryBounds } from "./geometry";

/**
 * Group nearby hail features into location clusters.
 *
 * Features within ~0.5 degrees (~50km) of each other are clustered together.
 * Returns locations sorted by maximum threshold (most severe first).
 *
 * Example:
 *   Input: [feature1 at [-95, 35], feature2 at [-95.2, 35.1], feature3 at [-100, 40]]
 *   Output: [
 *     { id: 0, lat: 35.05, lng: -95.1, maxThreshold: 2.0, thresholds: [2.0, 1.5], ... },
 *     { id: 1, lat: 40, lng: -100, maxThreshold: 1.0, thresholds: [1.0], ... }
 *   ]
 */
export function clusterFeatures(features: any[]): HailLocation[] {
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

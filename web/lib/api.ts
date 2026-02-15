import { API_BASE } from "./constants";

/**
 * Fetch hail swath polygons from the backend API.
 *
 * Returns a GeoJSON FeatureCollection with hail exposure polygons
 * for the given time window.
 *
 * Example:
 *   const geojson = await fetchSwathsData("2024-05-22T20:00:00Z", "2024-05-22T22:00:00Z");
 *
 * Throws an error if the API request fails.
 */
export async function fetchSwathsData(
  startTime: string,
  endTime: string
): Promise<any> {
  const url = `${API_BASE}/swaths?start_time=${startTime}&end_time=${endTime}`;
  const response = await fetch(url);

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `API returned ${response.status}`);
  }

  return response.json();
}

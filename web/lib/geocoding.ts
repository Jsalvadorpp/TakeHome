/**
 * Reverse geocode a lat/lng to get a human-readable location name.
 *
 * Uses OpenStreetMap Nominatim API (free, no API key required).
 * Returns city and state if available, empty string on error.
 *
 * Example:
 *   Input:  lat=35.5, lng=-95.5
 *   Output: "Oklahoma City, Oklahoma"
 *
 * Note: Nominatim has a rate limit of 1 request per second.
 * Callers should add delays between requests.
 */
export async function reverseGeocode(
  lat: number,
  lng: number
): Promise<string> {
  try {
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json&zoom=10&addressdetails=1`
    );
    if (!resp.ok) return "";

    const data = await resp.json();
    const addr = data.address || {};
    const city =
      addr.city || addr.town || addr.village || addr.hamlet || addr.county || "";
    const state = addr.state || "";
    return city && state ? `${city}, ${state}` : city || state || "";
  } catch {
    return "";
  }
}

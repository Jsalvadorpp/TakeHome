/**
 * Format an ISO timestamp as HH:MM time in UTC.
 *
 * Example:
 *   Input:  "2024-05-22T20:30:00Z"
 *   Output: "20:30"
 *
 * Returns the original string if parsing fails.
 */
export function formatTime(iso: string): string {
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

import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

dayjs.extend(utc);

/**
 * Render a backend timestamp in the viewer's locale and timezone.
 *
 * hyperglass timestamps arrive as *naive UTC* — no timezone suffix, e.g.
 * `2026-06-09T14:44:02` or the space-separated `2026-06-09 14:44:02`. Passing
 * those straight to `new Date()` parses them as local time, so the value would
 * never actually convert to the viewer's timezone. We parse as UTC first, then
 * format with the browser's locale + timezone via `toLocaleString` — which also
 * means the 12-/24-hour convention follows the viewer's locale settings rather
 * than being forced either way.
 *
 * Numbers are treated as epoch milliseconds (already absolute, e.g. history
 * `savedAt`). Unparseable input is returned unchanged rather than showing
 * "Invalid Date".
 */
export function formatTimestamp(value: string | number | Date): string {
  // Normalize the space-separated backend format to ISO 8601 ("YYYY-MM-DD HH:mm:ss"
  // -> "...THH:mm:ss") so dayjs.utc parses it deterministically rather than via
  // its lenient native fallback.
  const normalized = typeof value === 'string' ? value.replace(' ', 'T') : value;
  const parsed = typeof normalized === 'string' ? dayjs.utc(normalized) : dayjs(normalized);
  if (!parsed.isValid()) {
    return String(value);
  }
  return parsed.toDate().toLocaleString();
}

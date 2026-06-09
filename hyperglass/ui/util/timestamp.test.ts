import { describe, expect, it } from 'vitest';
import { formatTimestamp } from './timestamp';

describe('formatTimestamp', () => {
  // The backend emits naive UTC timestamps (no tz suffix), so the helper must
  // parse them AS UTC and then render via the locale default (no forced hour
  // cycle). We compare against an instant built with Date.UTC + plain
  // toLocaleString so the assertion holds in any runner timezone/locale.
  const expectedFor = (utc: Date) => utc.toLocaleString();

  it('parses an ISO-without-Z value as UTC, not local', () => {
    const instant = new Date(Date.UTC(2020, 3, 18, 14, 45, 37));
    expect(formatTimestamp('2020-04-18T14:45:37')).toBe(expectedFor(instant));
  });

  it('parses the space-separated backend format (no "T") as UTC too', () => {
    const instant = new Date(Date.UTC(2020, 3, 18, 14, 45, 37));
    expect(formatTimestamp('2020-04-18 14:45:37')).toBe(expectedFor(instant));
  });

  it('treats an epoch-millisecond number as an absolute instant', () => {
    const ms = Date.UTC(2026, 5, 9, 0, 0, 0);
    expect(formatTimestamp(ms)).toBe(expectedFor(new Date(ms)));
  });

  it('follows the locale default rather than forcing an hour cycle', () => {
    // No hour12 override: the output must equal the plain locale rendering of
    // the same UTC instant, so the 12-/24-hour choice tracks the viewer's locale.
    const instant = new Date(Date.UTC(2020, 3, 18, 23, 30, 0));
    expect(formatTimestamp('2020-04-18T23:30:00')).toBe(instant.toLocaleString());
  });

  it('returns the original value unchanged when it cannot be parsed', () => {
    expect(formatTimestamp('not-a-date')).toBe('not-a-date');
  });
});

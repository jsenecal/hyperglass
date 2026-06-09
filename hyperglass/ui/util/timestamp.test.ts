import { describe, expect, it } from 'vitest';
import { formatTimestamp } from './timestamp';

describe('formatTimestamp', () => {
  // The backend emits naive UTC timestamps (no tz suffix), so the helper must
  // parse them AS UTC and then render in the viewer's locale + timezone. We
  // compare against an instant built with Date.UTC so the assertion holds in
  // any runner timezone.
  const expectedFor = (utc: Date) => utc.toLocaleString(undefined, { hour12: false });

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

  it('uses 24-hour time (no AM/PM)', () => {
    const out = formatTimestamp('2020-04-18T23:30:00');
    expect(out).not.toMatch(/\b[AP]M\b/i);
  });

  it('returns the original value unchanged when it cannot be parsed', () => {
    expect(formatTimestamp('not-a-date')).toBe('not-a-date');
  });
});

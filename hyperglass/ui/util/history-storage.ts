import type { StateStorage } from 'zustand/middleware';

/**
 * Incrementally shrink a serialized persisted-history blob to fit under the
 * localStorage quota: first strip `output` from the oldest entry that still has
 * one, then (when no outputs remain) drop the oldest entry. Returns the new
 * serialized string, or null when nothing remains / input is unparseable.
 */
export function shrinkSerialized(serialized: string): string | null {
  let parsed: { state?: { entries?: unknown[] } };
  try {
    parsed = JSON.parse(serialized);
  } catch {
    return null;
  }
  const entries = parsed?.state?.entries;
  if (!Array.isArray(entries) || entries.length === 0) {
    return null;
  }
  // Entries are stored newest-first, so the oldest is at the end.
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i] as { results?: Record<string, { output?: unknown }> };
    const results = entry.results ?? {};
    for (const key of Object.keys(results)) {
      if (results[key] && 'output' in results[key]) {
        // biome-ignore lint/performance/noDelete: key must be absent (not undefined) so JSON.stringify omits it; verified by test
        delete results[key].output;
        return JSON.stringify(parsed);
      }
    }
  }
  entries.pop();
  return JSON.stringify(parsed);
}

/**
 * A zustand StateStorage backed by localStorage that never throws: reads and
 * writes are guarded, and a QuotaExceededError on write triggers incremental
 * shrink-and-retry via shrinkSerialized.
 */
export const historyStorage: StateStorage = {
  getItem(name: string): string | null {
    try {
      return typeof window === 'undefined' ? null : window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem(name: string, value: string): void {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(name, value);
      return;
    } catch {
      let current: string | null = value;
      // Shrink until it fits or there is nothing left to store.
      while (current !== null) {
        current = shrinkSerialized(current);
        if (current === null) {
          try {
            window.localStorage.removeItem(name);
          } catch {
            /* ignore */
          }
          return;
        }
        try {
          window.localStorage.setItem(name, current);
          return;
        } catch {
          /* keep shrinking */
        }
      }
    }
  },
  removeItem(name: string): void {
    try {
      if (typeof window !== 'undefined') window.localStorage.removeItem(name);
    } catch {
      /* ignore */
    }
  },
};

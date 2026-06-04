import { beforeEach, describe, expect, it, vi } from 'vitest';

// Upgrade-path guard for the zustand v3 → v5 migration: real users have a
// greeting payload in localStorage that was WRITTEN BY zustand v3's persist
// middleware — `JSON.stringify({ state, version: 0 })` (verified against the
// v3.7.2 source). v5 must rehydrate that payload as-is, with no `migrate`
// configured, or every user gets re-prompted after upgrading. The store is
// created at import time, so each test seeds storage first and then imports
// a fresh copy of the module.

beforeEach(() => {
  vi.resetModules();
  localStorage.clear();
});

describe('useGreeting rehydration from a zustand v3 payload', () => {
  it('rehydrates an acknowledged greeting written by v3', async () => {
    localStorage.setItem(
      'hyperglass-greeting',
      JSON.stringify({ state: { isAck: true, isOpen: false, greetingReady: true }, version: 0 }),
    );
    const { useGreeting } = await import('./use-greeting');
    const { isAck, isOpen, greetingReady } = useGreeting.getState();
    expect(isAck).toBe(true);
    expect(greetingReady).toBe(true);
    expect(isOpen).toBe(false);
  });

  it('falls back to defaults when nothing is persisted', async () => {
    const { useGreeting } = await import('./use-greeting');
    const { isAck, isOpen, greetingReady } = useGreeting.getState();
    expect(isAck).toBe(false);
    expect(greetingReady).toBe(false);
    expect(isOpen).toBe(false);
  });

  it('preserves store actions over a v3 payload that serialized none', async () => {
    // v3 JSON.stringify dropped functions from the persisted state; the v5
    // default merge must keep the current store's actions intact.
    localStorage.setItem(
      'hyperglass-greeting',
      JSON.stringify({ state: { isAck: true, isOpen: false, greetingReady: true }, version: 0 }),
    );
    const { useGreeting } = await import('./use-greeting');
    expect(typeof useGreeting.getState().ack).toBe('function');
    expect(typeof useGreeting.getState().open).toBe('function');
    expect(typeof useGreeting.getState().close).toBe('function');
  });
});

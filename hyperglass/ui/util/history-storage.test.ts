import { describe, expect, it } from 'vitest';
import { shrinkSerialized } from './history-storage';

const make = (entries: unknown[]) => JSON.stringify({ state: { entries }, version: 1 });

describe('shrinkSerialized', () => {
  it('strips output from the oldest entry that still has one', () => {
    const serialized = make([
      { id: 'new', results: { d1: { output: 'A' } } },
      { id: 'old', results: { d1: { output: 'B' } } },
    ]);
    const out = JSON.parse(shrinkSerialized(serialized) as string);
    // oldest (last) entry stripped first
    expect('output' in out.state.entries[1].results.d1).toBe(false);
    expect(out.state.entries[0].results.d1.output).toBe('A');
  });

  it('drops the oldest entry once no outputs remain to strip', () => {
    const serialized = make([
      { id: 'new', results: { d1: {} } },
      { id: 'old', results: { d1: {} } },
    ]);
    const out = JSON.parse(shrinkSerialized(serialized) as string);
    expect(out.state.entries).toHaveLength(1);
    expect(out.state.entries[0].id).toBe('new');
  });

  it('returns null when nothing remains', () => {
    expect(shrinkSerialized(make([]))).toBeNull();
    expect(shrinkSerialized('not json')).toBeNull();
  });
});

import { describe, it, expect, beforeEach } from 'vitest';
import { useQueryHistory } from './use-query-history';
import type { RecordInput } from './use-query-history';

const snapshot = (output: string) => ({
  id: 'cache-1',
  output,
  format: 'text/plain' as const,
  level: 'success' as const,
  timestamp: 'now',
  runtime: 1,
  cached: false,
  keywords: [] as string[],
  queryLabels: { location: 'Core 1', type: 'BGP Route' },
});

const input = (over: Partial<RecordInput> = {}): RecordInput => ({
  submissionId: 's1',
  deviceId: 'core1',
  deviceLabel: 'Core 1',
  query: { queryType: 'bgp_route', queryTarget: ['8.8.8.0/24'] },
  labels: { type: 'BGP Route', target: '8.8.8.0/24' },
  snapshot: snapshot('A'),
  limit: 10,
  ...over,
});

beforeEach(() => {
  useQueryHistory.setState({ entries: [], openId: null });
  window.localStorage.clear();
});

describe('useQueryHistory.record', () => {
  it('creates an entry keyed by submissionId', () => {
    useQueryHistory.getState().record(input());
    const { entries } = useQueryHistory.getState();
    expect(entries).toHaveLength(1);
    expect(entries[0].id).toBe('s1');
    expect(entries[0].results.core1.output).toBe('A');
    expect(entries[0].query.queryLocation).toEqual(['core1']);
  });

  it('groups multiple devices of the same submission into one entry', () => {
    useQueryHistory.getState().record(input());
    useQueryHistory
      .getState()
      .record(input({ deviceId: 'edge2', deviceLabel: 'Edge 2', snapshot: snapshot('B') }));
    const { entries } = useQueryHistory.getState();
    expect(entries).toHaveLength(1);
    expect(Object.keys(entries[0].results).sort()).toEqual(['core1', 'edge2']);
    expect(entries[0].query.queryLocation.sort()).toEqual(['core1', 'edge2']);
  });

  it('keeps distinct submissions as separate entries, newest first', () => {
    useQueryHistory.getState().record(input({ submissionId: 's1' }));
    useQueryHistory.getState().record(input({ submissionId: 's2' }));
    const { entries } = useQueryHistory.getState();
    expect(entries.map(e => e.id)).toEqual(['s2', 's1']);
  });

  it('enforces the limit, evicting oldest', () => {
    for (let i = 0; i < 12; i++) {
      useQueryHistory.getState().record(input({ submissionId: `s${i}`, limit: 10 }));
    }
    const { entries } = useQueryHistory.getState();
    expect(entries).toHaveLength(10);
    expect(entries[0].id).toBe('s11');
    expect(entries.find(e => e.id === 's0')).toBeUndefined();
  });
});

describe('useQueryHistory remove/clear/open/close', () => {
  it('remove deletes by id', () => {
    useQueryHistory.getState().record(input({ submissionId: 's1' }));
    useQueryHistory.getState().record(input({ submissionId: 's2' }));
    useQueryHistory.getState().remove('s1');
    expect(useQueryHistory.getState().entries.map(e => e.id)).toEqual(['s2']);
  });

  it('clear empties entries', () => {
    useQueryHistory.getState().record(input());
    useQueryHistory.getState().clear();
    expect(useQueryHistory.getState().entries).toHaveLength(0);
  });

  it('open/close set and reset openId', () => {
    useQueryHistory.getState().open('s1');
    expect(useQueryHistory.getState().openId).toBe('s1');
    useQueryHistory.getState().close();
    expect(useQueryHistory.getState().openId).toBeNull();
  });
});

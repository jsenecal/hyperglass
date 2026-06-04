import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useRecordHistory } from './use-record-history';
import { useQueryHistory } from './use-query-history';

const recordSpy = vi.fn();

vi.mock('~/context', () => ({
  useConfig: () => ({ cache: { historyEnabled: true, historyLimit: 10 } }),
}));

beforeEach(() => {
  recordSpy.mockClear();
  useQueryHistory.setState({
    entries: [],
    openId: null,
    record: recordSpy,
  } as never);
});

const payload = {
  submissionId: 's1',
  deviceId: 'core1',
  deviceLabel: 'Core 1',
  directiveHistory: true,
  query: { queryType: 'bgp_route', queryTarget: ['x'] },
  labels: { type: 'BGP Route', target: 'x' },
  snapshot: {} as never,
};

describe('useRecordHistory', () => {
  it('records when global + directive both allow it', () => {
    const { result } = renderHook(() => useRecordHistory());
    result.current(payload);
    expect(recordSpy).toHaveBeenCalledOnce();
    expect(recordSpy.mock.calls[0][0].limit).toBe(10);
  });

  it('no-ops when the directive opts out', () => {
    const { result } = renderHook(() => useRecordHistory());
    result.current({ ...payload, directiveHistory: false });
    expect(recordSpy).not.toHaveBeenCalled();
  });
});

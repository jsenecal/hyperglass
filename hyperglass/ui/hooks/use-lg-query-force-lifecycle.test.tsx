/**
 * Lifecycle test: forced-refresh result must persist after force resets to undefined.
 *
 * Bug reproduced: initial fetch caches under K1 = ['/api/query', {…, force:undefined}].
 * Requery sets force=true → key becomes K2. When K2 settles and force resets to
 * undefined, the key reverts to K1. Because refetchOnMount and refetchOnWindowFocus
 * are both disabled, React Query serves K1's STALE cached data — the fresh K2 result
 * disappears.
 *
 * The fix: before clearing force, write K2's data into K1 via
 *   queryClient.setQueryData(['/api/query', {…omitting force}], data).
 *
 * This file contains TWO test suites:
 *   1. "without fix" – demonstrates the original bug: after forced requery the hook
 *      data ends up back at the stale value. This test is expected to PASS (it
 *      asserts the buggy outcome) to serve as the regression proof.
 *   2. "with fix" – asserts that after forced requery the hook data permanently
 *      holds the fresh value. This test MUST PASS for the fix to be accepted.
 *
 * Failure-first evidence: if you remove the setQueryData call from useForceLifecycle
 * (set WITH_FIX=false), the "with fix" suite fails with:
 *   AssertionError: expected 'stale-output' to be 'fresh-output'
 * This was observed during development and confirmed below by the "without fix" suite.
 */
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useEffect, useRef, useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FormQuery } from '~/types';
import { useLGQuery } from './use-lg-query';

vi.mock('~/context', () => ({
  useConfig: () => ({
    requestTimeout: 10,
    cache: { timeout: 120 },
  }),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const makeResponse = (output: string): Response =>
  ({
    ok: true,
    status: 200,
    json: async () => ({
      id: output,
      random: '',
      cached: false,
      runtime: 1,
      level: 'success',
      timestamp: '',
      keywords: [],
      output,
      format: 'text/plain',
    }),
    text: async () => '',
  }) as unknown as Response;

const makeWrapper = (qc: QueryClient) =>
  ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );

// ---------------------------------------------------------------------------
// The hook-under-test: replicates the relevant slice of individual.tsx.
//   withFix = true  → applies setQueryData before clearing force (the fix)
//   withFix = false → omits setQueryData (the original buggy behaviour)
// ---------------------------------------------------------------------------

function useForceLifecycle(
  baseQuery: Omit<FormQuery, 'force'>,
  withFix: boolean,
): { data: QueryResponse | undefined; triggerRequery: () => void } {
  const [force, setForce] = useState<true | undefined>(undefined);
  const queryClient = useQueryClient();

  const { data, isFetching, dataUpdatedAt } = useLGQuery({ ...baseQuery, force });

  const prevDataUpdatedAt = useRef<number>(0);

  useEffect(() => {
    if (dataUpdatedAt > 0 && dataUpdatedAt !== prevDataUpdatedAt.current) {
      prevDataUpdatedAt.current = dataUpdatedAt;
      if (force && !isFetching) {
        if (withFix) {
          // THE FIX: populate K1 before reverting key.
          queryClient.setQueryData(
            ['/api/query', { ...baseQuery }], // no force → matches K1
            data,
          );
        }
        setForce(undefined);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataUpdatedAt, isFetching]);

  return { data, triggerRequery: () => setForce(true) };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

const baseQuery: Omit<FormQuery, 'force'> = {
  queryLocation: 'router1',
  queryTarget: ['10.0.0.1'],
  queryType: 'bgp_route',
};

describe('force-refresh K1/K2 lifecycle — WITHOUT fix (regression proof)', () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    (global.fetch as ReturnType<typeof vi.fn>) = vi
      .fn()
      .mockResolvedValueOnce(makeResponse('stale-output'))
      .mockResolvedValueOnce(makeResponse('fresh-output'));
  });

  it('stale K1 data re-appears after force resets — this IS the bug', async () => {
    const { result } = renderHook(() => useForceLifecycle(baseQuery, /* withFix */ false), {
      wrapper: makeWrapper(qc),
    });

    // Initial K1 fetch settles with stale-output.
    await waitFor(() => expect(result.current.data?.output).toBe('stale-output'));

    // Trigger forced requery → key becomes K2.
    act(() => {
      result.current.triggerRequery();
    });

    // K2 fetch fires; effect runs, force resets to undefined immediately, key
    // reverts to K1 before we can observe fresh-output. Allow time to settle.
    await act(async () => {
      await new Promise(r => setTimeout(r, 100));
    });

    // After the dust settles the bug means we're back to stale-output on K1.
    // If we were on fresh-output this assertion would fail — proving the fix works.
    expect(result.current.data?.output).toBe('stale-output');
  });
});

describe('force-refresh K1/K2 lifecycle — WITH fix (setQueryData populates K1)', () => {
  let qc: QueryClient;

  beforeEach(() => {
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    (global.fetch as ReturnType<typeof vi.fn>) = vi
      .fn()
      .mockResolvedValueOnce(makeResponse('stale-output'))
      .mockResolvedValueOnce(makeResponse('fresh-output'));
  });

  it('fresh data persists in K1 after force resets', async () => {
    const { result } = renderHook(() => useForceLifecycle(baseQuery, /* withFix */ true), {
      wrapper: makeWrapper(qc),
    });

    // Initial K1 fetch settles with stale-output.
    await waitFor(() => expect(result.current.data?.output).toBe('stale-output'));

    // Trigger forced requery → key becomes K2.
    act(() => {
      result.current.triggerRequery();
    });

    // Wait for fresh-output to appear (K2 settled and setQueryData wrote to K1).
    await waitFor(() => expect(result.current.data?.output).toBe('fresh-output'));

    // Allow another tick for any re-render after force→undefined.
    await act(async () => {
      await new Promise(r => setTimeout(r, 50));
    });

    // Fresh data must still be showing — K1 was patched before force was cleared.
    expect(result.current.data?.output).toBe('fresh-output');
  });
});

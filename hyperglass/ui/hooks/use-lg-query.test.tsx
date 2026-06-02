/**
 * Tests for useLGQuery's force flag pass-through.
 *
 * Pattern: mock global.fetch per-test with vi.fn() (same as use-share.test.tsx).
 * The hook reads requestTimeout and cache from useConfig(); we mock ~/context to
 * return a minimal Config so no real provider tree is needed.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { FormQuery } from '~/types';
import { useLGQuery } from './use-lg-query';

// Provide a minimal config that satisfies useLGQuery's useConfig() call.
vi.mock('~/context', () => ({
  useConfig: () => ({
    requestTimeout: 10,
    cache: { timeout: 120 },
  }),
}));

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const mockQueryResponse = (): Response =>
  ({
    ok: true,
    status: 200,
    json: async () => ({
      id: 'x',
      random: '',
      cached: false,
      runtime: 1,
      level: 'success',
      timestamp: '',
      keywords: [],
      output: 'ok',
      format: 'text/plain',
    }),
    text: async () => '',
  }) as unknown as Response;

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue(mockQueryResponse());
});

describe('useLGQuery force flag', () => {
  it('omits force from body when not set', async () => {
    const query: FormQuery = { queryLocation: 'test1', queryTarget: ['1.2.3.4'], queryType: 'bgp' };
    renderHook(() => useLGQuery(query), { wrapper });
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const body = JSON.parse((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(body.force).toBeUndefined();
  });

  it('includes force=true in body when set', async () => {
    const query: FormQuery = {
      queryLocation: 'test1',
      queryTarget: ['1.2.3.4'],
      queryType: 'bgp',
      force: true,
    };
    renderHook(() => useLGQuery(query), { wrapper });
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const body = JSON.parse((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1].body);
    expect(body.force).toBe(true);
  });
});

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
/**
 * Tests for useShareCreate / useShareGet.
 *
 * Pattern: mock global.fetch per-test with vi.fn(). Resets between tests via
 * beforeEach. This is intentionally different from use-dns-query.test.tsx,
 * which hits the real network — share hooks call internal API endpoints where
 * a live server would be required; per-test fetch mocking is the right trade-off
 * here. Future contributors adding hooks that call internal /api/* routes should
 * follow this pattern rather than the real-network pattern.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ShareError, useShareCreate, useShareGet } from './use-share';

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const mockResponse = (overrides: Partial<Response>) =>
  ({
    ok: true,
    status: 200,
    json: async () => ({}),
    text: async () => '',
    ...overrides,
  }) as unknown as Response;

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('useShareCreate', () => {
  it('POSTs to /api/query/share/<cacheId> and returns the response', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({
        json: async () => ({
          id: 'aaaaaaaaaaa',
          url: 'https://x/result/aaaaaaaaaaa',
          expiresAt: '2026-05-08T00:00:00Z',
        }),
      }),
    );
    const { result } = renderHook(() => useShareCreate(), { wrapper });
    result.current.mutate('hyperglass.query.deadbeef');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/query/share/hyperglass.query.deadbeef',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result.current.data?.id).toBe('aaaaaaaaaaa');
  });

  it('surfaces 410 as a ShareError with status', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({ ok: false, status: 410 }),
    );
    const { result } = renderHook(() => useShareCreate(), { wrapper });
    result.current.mutate('expired-id');
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as ShareError).status).toBe(410);
  });
});

describe('useShareGet', () => {
  it('GETs /api/query/share/<id> and returns the snapshot', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({
        json: async () => ({
          id: 'aaa',
          shared: true,
          output: 'x',
          cached: true,
          runtime: 1,
          timestamp: '',
          format: 'text/plain',
          level: 'success',
          keywords: [],
          query: {},
          queryLabels: {},
          createdAt: '',
          expiresAt: '',
        }),
      }),
    );
    const { result } = renderHook(() => useShareGet('aaa'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(global.fetch).toHaveBeenCalledWith('/api/query/share/aaa');
    expect(result.current.data?.shared).toBe(true);
  });

  it('does not fetch when shareId is undefined (enabled: false)', async () => {
    renderHook(() => useShareGet(undefined), { wrapper });
    // Yield a tick so React Query has a chance to fire (it should not).
    await new Promise(r => setTimeout(r, 0));
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// jsdom does not implement window.matchMedia; Chakra UI's useBreakpointValue requires it.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

import ResultPage from '../../../pages/result/[id]';

vi.mock('next/router', () => ({
  useRouter: () => ({
    query: { id: 'aaaaaaaaaaa' },
    isReady: true,
    push: vi.fn(),
  }),
}));

vi.mock('~/context', () => ({
  useConfig: () => ({
    cache: {
      timeout: 600,
      shareEnabled: true,
      shareTimeout: 604800,
      refreshMinInterval: 120,
      showText: false,
    },
    web: {
      text: {
        shareSnapshotBanner: 'Snapshot taken at {timestamp}',
        shareNotFound: 'Share not found or expired.',
        shareRunFreshQuery: 'Run a fresh query',
        shareExpiresAt: 'Expires {expires}',
        cacheIcon: 'Cached at {time}',
        cachePrefix: 'Cached',
        completeTime: 'Completed in {seconds}',
        requeryTooltip: 'Reload Query',
        refreshCooldown: 'Wait {seconds}s',
        shareButton: 'Share',
        sharePopoverTitle: 'Share this result',
        shareCopyLink: 'Copy link',
        shareLinkCopied: 'Copied!',
        shareCreateError: 'Could not create share link.',
        shareCreateExpired: 'Result expired. Refresh and try again.',
      },
      highlight: [],
    },
    messages: {
      general: 'An error occurred.',
      requestTimeout: 'Request timed out.',
      noOutput: 'No output.',
    },
    devices: [],
    parsedDataFields: [],
  }),
  HyperglassContext: { Provider: ({ children }: { children: React.ReactNode }) => children },
  queryClient: new QueryClient(),
}));

const fakeSnapshot = {
  id: 'aaaaaaaaaaa',
  shared: true,
  cached: true,
  output: 'BGP table output here',
  runtime: 1,
  timestamp: '2026-05-01 12:00:00',
  format: 'text/plain',
  level: 'success' as const,
  keywords: [],
  query: {
    query_location: 'test1',
    query_target: '192.0.2.0/24',
    query_type: 'juniper_bgp_route',
  },
  queryLabels: { location: 'test1', type: 'BGP Route' },
  createdAt: '2026-05-01T12:00:00Z',
  expiresAt: '2026-05-08T12:00:00Z',
};

const mockResponse = (overrides: Partial<Response>) =>
  ({
    ok: true,
    status: 200,
    json: async () => fakeSnapshot,
    text: async () => '',
    ...overrides,
  }) as unknown as Response;

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <ChakraProvider>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </ChakraProvider>
  );
};

beforeEach(() => {
  global.fetch = vi.fn();
});

describe('ResultPage', () => {
  it('renders the snapshot output for a valid id', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse({}));

    render(<ResultPage />, { wrapper });

    // Banner with configured text
    await waitFor(() => expect(screen.getByText(/Snapshot taken at/i)).toBeInTheDocument());

    // Output text rendered in the component
    await waitFor(() => expect(screen.getByText(/BGP table output here/)).toBeInTheDocument());
  });

  it('shows configured "share not found" message on 404', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({ ok: false, status: 404, json: async () => ({ detail: 'Not found' }) }),
    );

    render(<ResultPage />, { wrapper });

    await waitFor(() =>
      expect(screen.getByText('Share not found or expired.')).toBeInTheDocument(),
    );
  });

  it('exposes a "Run a fresh query" link with prefilled query string', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse({}));

    render(<ResultPage />, { wrapper });

    const link = await screen.findByRole('link', { name: /Run a fresh query/i });
    expect(link).toBeInTheDocument();

    const href = link.getAttribute('href') ?? '';
    expect(href).toMatch(/location=test1/);
    expect(href).toMatch(/target=192\.0\.2\.0%2F24/);
    expect(href).toMatch(/type=juniper_bgp_route/);
  });
});

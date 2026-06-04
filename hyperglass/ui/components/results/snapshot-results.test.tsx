import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

// jsdom does not implement window.matchMedia; Chakra UI requires it.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((q: string) => ({
    matches: false,
    media: q,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

vi.mock('./share-button', () => ({
  ShareButton: () => <div data-testid="share-button" />,
}));

vi.mock('~/context', () => ({
  useConfig: () => ({
    devices: [],
    web: {
      highlight: [],
      text: {
        cacheIcon: '',
        cachePrefix: 'Cached',
        completeTime: 'Completed in {time}',
        requeryTooltip: 'Reload Query',
        refreshCooldown: 'Wait {seconds}s',
        shareButton: 'Share',
        sharePopoverTitle: 'Share this result',
        shareCopyLink: 'Copy link',
        shareLinkCopied: 'Copied!',
        shareExpiresAt: 'Expires {expires}',
        shareCreateError: 'Could not create share link.',
        shareCreateExpired: 'Result expired.',
        shareNotFound: 'Result not found.',
        shareSnapshotBanner: 'Snapshot',
        shareRunFreshQuery: 'Run a fresh query',
      },
    },
    messages: {
      general: 'An error occurred.',
      requestTimeout: 'Request timed out.',
      noOutput: 'No output.',
    },
    cache: {
      showText: true,
      timeout: 600,
      shareEnabled: true,
      shareTimeout: 604800,
      refreshMinInterval: 120,
    },
  }),
}));

import { SnapshotResults } from './snapshot-results';

const snap = (location: string, output: string) =>
  ({
    id: `c-${location}`,
    output,
    format: 'text/plain',
    level: 'success',
    timestamp: 'now',
    runtime: 1,
    cached: true,
    keywords: [],
    queryLabels: { location, type: 'BGP Route' },
  }) as never;

const Providers = ({ children }: { children: React.ReactNode }) => (
  <ChakraProvider>
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  </ChakraProvider>
);

it('renders one result per item', () => {
  render(
    <Providers>
      <SnapshotResults
        items={[
          { queryLocation: 'core1', snapshot: snap('Core 1', 'A') },
          { queryLocation: 'edge2', snapshot: snap('Edge 2', 'B') },
        ]}
      />
    </Providers>,
  );
  expect(screen.getByText('Core 1')).toBeInTheDocument();
  expect(screen.getByText('Edge 2')).toBeInTheDocument();
});

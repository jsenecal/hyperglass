import { Accordion, ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

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

import { Result } from './individual';

const snapshot = {
  id: 'cache-1',
  output: 'hello',
  format: 'text/plain',
  level: 'success',
  timestamp: 'now',
  runtime: 1,
  cached: true,
  keywords: [],
  queryLabels: { location: 'Core 1', type: 'BGP Route' },
} as never;

const renderResult = (props: Record<string, unknown>) =>
  render(
    <ChakraProvider>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Accordion>
          <Result index={0} queryLocation="core1" snapshot={snapshot} {...props} />
        </Accordion>
      </QueryClientProvider>
    </ChakraProvider>,
  );

describe('Result share visibility', () => {
  it('hides Share when readOnly and showShare not set', () => {
    renderResult({ readOnly: true });
    expect(screen.queryByTestId('share-button')).not.toBeInTheDocument();
  });

  it('shows Share in history mode (readOnly + showShare)', () => {
    renderResult({ readOnly: true, showShare: true });
    expect(screen.getByTestId('share-button')).toBeInTheDocument();
  });
});

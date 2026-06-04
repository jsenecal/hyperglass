import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

vi.mock('~/components/results/share-button', () => ({
  ShareButton: () => <div data-testid="share-button" />,
}));

vi.mock('~/context', () => ({
  useConfig: () => ({
    devices: [],
    web: {
      text: {
        historyOpen: 'Open',
        historyRerun: 'Run again',
        historyNewTarget: 'Run with a new target',
        historyDelete: 'Delete',
      },
    },
    messages: {
      historyDeviceUnavailable: 'Device unavailable.',
    },
  }),
}));

import { useQueryHistory } from '~/hooks/use-query-history';
import type { HistoryEntry } from '~/hooks/use-query-history';
import { HistoryEntryRow } from './history-entry-row';

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const snapshot = (id: string): ResultSnapshot =>
  ({
    id,
    output: 'some output',
    format: 'text/plain',
    level: 'success',
    timestamp: new Date().toISOString(),
    runtime: 1,
    cached: false,
    keywords: [],
    queryLabels: { location: 'Core 1', type: 'BGP Route' },
  }) as never;

const singleEntry: HistoryEntry = {
  id: 'entry-single',
  savedAt: Date.now() - 60_000,
  query: { queryLocation: ['core1'], queryType: 'bgp_route', queryTarget: ['192.0.2.1'] },
  labels: { locations: ['Core 1'], type: 'BGP Route', target: '192.0.2.1' },
  results: { core1: snapshot('cache-single') },
};

const multiEntry: HistoryEntry = {
  id: 'entry-multi',
  savedAt: Date.now() - 120_000,
  query: {
    queryLocation: ['core1', 'edge2'],
    queryType: 'bgp_route',
    queryTarget: ['192.0.2.1'],
  },
  labels: { locations: ['Core 1', 'Edge 2'], type: 'BGP Route', target: '192.0.2.1' },
  results: {
    core1: snapshot('cache-multi-1'),
    edge2: snapshot('cache-multi-2'),
  },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const renderRow = (entry: HistoryEntry) =>
  render(
    <ChakraProvider>
      <HistoryEntryRow entry={entry} />
    </ChakraProvider>,
  );

beforeEach(() => {
  useQueryHistory.setState({ entries: [singleEntry, multiEntry], openId: null });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('HistoryEntryRow', () => {
  it('renders the ShareButton sentinel for a single-device entry', () => {
    renderRow(singleEntry);
    expect(screen.getByTestId('share-button')).toBeInTheDocument();
  });

  it('does NOT render the ShareButton sentinel for a multi-device entry', () => {
    renderRow(multiEntry);
    expect(screen.queryByTestId('share-button')).not.toBeInTheDocument();
  });

  it('clicking Open sets openId on the store', () => {
    renderRow(singleEntry);
    fireEvent.click(screen.getByLabelText('Open'));
    expect(useQueryHistory.getState().openId).toBe(singleEntry.id);
  });

  it('clicking Delete removes the entry from the store', () => {
    renderRow(singleEntry);
    fireEvent.click(screen.getByLabelText('Delete'));
    const ids = useQueryHistory.getState().entries.map(e => e.id);
    expect(ids).not.toContain(singleEntry.id);
  });
});

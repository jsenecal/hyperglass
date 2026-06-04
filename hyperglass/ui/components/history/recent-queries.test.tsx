import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
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

vi.mock('~/context', () => ({
  useConfig: () => ({
    cache: { historyEnabled: true },
    web: {
      text: {
        historyTitle: 'Recent queries',
        historyClearAll: 'Clear all',
        historyClearConfirm: 'Clear all saved queries?',
        historyBack: 'Back',
      },
    },
  }),
}));

vi.mock('./history-entry-row', () => ({
  HistoryEntryRow: ({
    entry,
  }: { entry: { labels: { locations: string[]; type: string; target: string } } }) => (
    <div data-testid="row">{`${entry.labels.locations.join(', ')} · ${entry.labels.type} · ${
      entry.labels.target
    }`}</div>
  ),
}));

import { useFormState } from '~/hooks/use-form-state';
import { useQueryHistory } from '~/hooks/use-query-history';
import { RecentQueries } from './recent-queries';

const entry = {
  id: 's1',
  savedAt: Date.now(),
  query: { queryLocation: ['core1'], queryType: 'bgp_route', queryTarget: ['8.8.8.0/24'] },
  labels: { locations: ['Core 1'], type: 'BGP Route', target: '8.8.8.0/24' },
  results: { core1: {} },
} as never;

const renderComponent = () =>
  render(
    <ChakraProvider>
      <RecentQueries />
    </ChakraProvider>,
  );

beforeEach(() => {
  useFormState.getState().reset();
  useQueryHistory.setState({ entries: [], openId: null });
});

describe('RecentQueries', () => {
  it('renders nothing when there are no entries', () => {
    const { container } = renderComponent();
    expect(container.querySelector('[data-testid="row"]')).toBeNull();
    expect(screen.queryByText('Recent queries')).not.toBeInTheDocument();
  });

  it('renders the title and a row when an entry exists', () => {
    useQueryHistory.setState({ entries: [entry], openId: null });
    renderComponent();
    expect(screen.getByText('Recent queries')).toBeInTheDocument();
    expect(screen.getByText(/Core 1 · BGP Route · 8.8.8.0\/24/)).toBeInTheDocument();
  });
});

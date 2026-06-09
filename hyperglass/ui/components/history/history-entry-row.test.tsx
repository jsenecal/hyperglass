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

// Mutable so individual tests can control which devices `useDevice` resolves.
const configState = vi.hoisted(() => ({ devices: [] as unknown[] }));

vi.mock('~/context', () => ({
  // useFormState.reset() evicts react-query caches via the context's queryClient.
  queryClient: { removeQueries: vi.fn() },
  useConfig: () => ({
    devices: configState.devices,
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

import { useFormState } from '~/hooks/use-form-state';
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

const device = (id: string, name: string) =>
  ({
    id,
    name,
    directives: [{ id: 'bgp_route', name: 'BGP Route', groups: ['ip'] }],
  }) as never;

// Shape consumed by useDevice: groups of locations.
const deviceGroup = {
  group: 'All Devices',
  locations: [device('core1', 'Core 1'), device('edge2', 'Edge 2')],
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

beforeEach(async () => {
  configState.devices = [deviceGroup];
  useQueryHistory.setState({ entries: [singleEntry, multiEntry], openId: null });
  await useFormState.getState().reset();
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

  it('clicking Re-run prefills the form, stamps a new submissionId, and shows results', () => {
    useFormState.getState().setSubmissionId('previous-submission');
    renderRow(singleEntry);
    fireEvent.click(screen.getByLabelText('Run again'));
    const state = useFormState.getState();
    expect(state.form.queryLocation).toEqual(['core1']);
    expect(state.form.queryType).toBe('bgp_route');
    expect(state.form.queryTarget).toEqual(['192.0.2.1']);
    expect(state.selections.queryType).toEqual({ value: 'bgp_route', label: 'BGP Route' });
    expect(state.submissionId).not.toBeNull();
    expect(state.submissionId).not.toBe('previous-submission');
    expect(state.status).toBe('results');
  });

  it('clicking New target prefills the form with queryTarget cleared and stays on the form', () => {
    useFormState.getState().setStatus('results');
    renderRow(singleEntry);
    fireEvent.click(screen.getByLabelText('Run with a new target'));
    const state = useFormState.getState();
    expect(state.form.queryLocation).toEqual(['core1']);
    expect(state.form.queryType).toBe('bgp_route');
    expect(state.form.queryTarget).toEqual([]);
    expect(state.selections.queryType).toEqual({ value: 'bgp_route', label: 'BGP Route' });
    expect(state.status).toBe('form');
    expect(state.submissionId).toBeNull();
  });

  it('Re-run aborts with a toast when no device resolves', async () => {
    configState.devices = [];
    renderRow(singleEntry);
    fireEvent.click(screen.getByLabelText('Run again'));
    expect(await screen.findByText('Device unavailable.')).toBeInTheDocument();
    const state = useFormState.getState();
    expect(state.submissionId).toBeNull();
    expect(state.status).toBe('form');
  });

  it('New target aborts with a toast when no device resolves', async () => {
    configState.devices = [];
    useFormState.getState().setStatus('results');
    renderRow(singleEntry);
    fireEvent.click(screen.getByLabelText('Run with a new target'));
    expect(await screen.findByText('Device unavailable.')).toBeInTheDocument();
    expect(useFormState.getState().status).toBe('results');
  });
});

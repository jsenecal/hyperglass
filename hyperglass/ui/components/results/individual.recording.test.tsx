/**
 * Tests that the history-recording effect in <Result> fires correctly:
 *   - Snapshot/read-only renders do NOT record.
 *   - A live successful result DOES record with the expected payload.
 *
 * These live in a separate file so their vi.mock() calls don't bleed into
 * individual.test.tsx, which uses different (or no) mocks for the same modules.
 */

import { Accordion, ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { render } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

// jsdom does not implement window.matchMedia; Chakra UI requires it.
// Use beforeAll + vi.stubGlobal so the stub persists across all tests
// and cannot be cleared by jsdom re-initialization between tests.
const matchMediaMock = vi.fn().mockImplementation((q: string) => ({
  matches: false,
  media: q,
  onchange: null,
  addListener: vi.fn(),
  removeListener: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(),
}));

beforeAll(() => {
  vi.stubGlobal('matchMedia', matchMediaMock);
});

// ── Module-level control variables ─────────────────────────────────────────
// vi.mock() is hoisted before imports; these variables let individual tests
// change what the mocked hooks return without re-importing the module.
const recordSpy = vi.fn();

// Default LG query result: still loading / no data.
// Cast through unknown to avoid a generic-parameter mismatch on refetch's
// TPageData type parameter — the mock never exercises refetch in these tests.
let lgQueryResult: ReturnType<typeof import('~/hooks').useLGQuery> = {
  data: undefined,
  error: null,
  isLoading: true,
  isFetching: true,
  isFetchedAfterMount: false,
  dataUpdatedAt: 0,
  refetch: vi.fn() as unknown as ReturnType<typeof import('~/hooks').useLGQuery>['refetch'],
} as unknown as ReturnType<typeof import('~/hooks').useLGQuery>;

// ── device group shape expected by useDevice (config.devices[].locations) ──
const testDirective = {
  id: 'bgp_route',
  name: 'BGP Route',
  fieldType: 'text' as const,
  description: '',
  groups: [],
  info: null,
  history: true,
};

const testDevice = {
  id: 'core1',
  name: 'Core 1',
  group: null,
  avatar: null,
  description: null,
  directives: [testDirective],
};

// ── Mocks (hoisted) ─────────────────────────────────────────────────────────

vi.mock('./share-button', () => ({
  ShareButton: () => <div data-testid="share-button" />,
}));

vi.mock('~/context', () => ({
  useConfig: () => ({
    requestTimeout: 30,
    devices: [{ group: null, locations: [testDevice] }],
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
      historyEnabled: true,
      historyLimit: 20,
    },
  }),
  // queryClient is used inside use-form-state's reset() — provide a stub.
  queryClient: {
    removeQueries: vi.fn(),
    setQueryData: vi.fn(),
  },
}));

vi.mock('~/hooks', async importOriginal => {
  const actual = await importOriginal<typeof import('~/hooks')>();
  return {
    ...actual,
    // useRecordHistory always returns our spy; guards inside the real hook are
    // bypassed intentionally — we only need to assert the effect calls it.
    useRecordHistory: () => recordSpy,
    // useLGQuery is controlled by lgQueryResult, mutated per-test.
    useLGQuery: () => lgQueryResult,
  };
});

// Import AFTER mocks are established.
import { useFormState } from '~/hooks/use-form-state';
import { Result } from './individual';

// ── Fixtures ────────────────────────────────────────────────────────────────

const snapshotFixture = {
  id: 'cache-snap',
  output: 'hello',
  format: 'text/plain',
  level: 'success',
  timestamp: 'now',
  runtime: 1,
  cached: true,
  keywords: [],
  queryLabels: { location: 'Core 1', type: 'BGP Route' },
} as never;

const successData: QueryResponse = {
  id: 'cache-1',
  random: '',
  output: 'hi',
  format: 'text/plain',
  level: 'success',
  timestamp: 'now',
  runtime: 1,
  cached: false,
  keywords: [],
};

// ── Render helper ────────────────────────────────────────────────────────────

function renderResult(props: Record<string, unknown>) {
  return render(
    <ChakraProvider>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <Accordion>
          <Result index={0} queryLocation="core1" {...props} />
        </Accordion>
      </QueryClientProvider>
    </ChakraProvider>,
  );
}

// ── Setup / teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  recordSpy.mockClear();
  // Reset to loading/no-data baseline.
  lgQueryResult = {
    data: undefined,
    error: null,
    isLoading: true,
    isFetching: true,
    isFetchedAfterMount: false,
    dataUpdatedAt: 0,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof import('~/hooks').useLGQuery>;
  // Reset form state.
  useFormState.setState({
    submissionId: null,
    form: { queryLocation: [], queryTarget: [], queryType: '' },
    filtered: { groups: [], types: [] },
  } as never);
});

afterEach(() => {
  // NOTE: Do NOT call vi.restoreAllMocks() here — it would restore (i.e. remove)
  // the vi.stubGlobal('matchMedia', ...) that Chakra's useMediaQuery requires,
  // causing the remaining tests to crash with "Cannot read properties of undefined".
});

// ── Tests ────────────────────────────────────────────────────────────────────

describe('Result history recording', () => {
  it('does NOT record when rendered in snapshot mode', () => {
    renderResult({ snapshot: snapshotFixture });
    expect(recordSpy).not.toHaveBeenCalled();
  });

  it('does NOT record when rendered in readOnly mode', () => {
    renderResult({ snapshot: snapshotFixture, readOnly: true });
    expect(recordSpy).not.toHaveBeenCalled();
  });

  it('records a successful live result with the expected payload', () => {
    // Set up LG query to return a settled successful response.
    lgQueryResult = {
      data: successData,
      error: null,
      isLoading: false,
      isFetching: false,
      isFetchedAfterMount: true,
      dataUpdatedAt: 1234,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof import('~/hooks').useLGQuery>;

    // Prime form state so the effect guard passes.
    useFormState.setState({
      submissionId: 's1',
      form: { queryLocation: ['core1'], queryTarget: ['8.8.8.0/24'], queryType: 'bgp_route' },
      filtered: { groups: [], types: [testDirective] },
    } as never);

    renderResult({});

    expect(recordSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        submissionId: 's1',
        deviceId: 'core1',
        deviceLabel: 'Core 1',
        directiveHistory: true,
        snapshot: expect.objectContaining({
          id: 'cache-1',
          level: 'success',
          queryLabels: { location: 'Core 1', type: 'BGP Route' },
        }),
      }),
    );
  });

  it('does NOT record when submissionId is null', () => {
    lgQueryResult = {
      data: successData,
      error: null,
      isLoading: false,
      isFetching: false,
      isFetchedAfterMount: true,
      dataUpdatedAt: 1234,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof import('~/hooks').useLGQuery>;
    // submissionId stays null from beforeEach.
    renderResult({});
    expect(recordSpy).not.toHaveBeenCalled();
  });

  it('does NOT record when the result level is not success', () => {
    lgQueryResult = {
      data: { ...successData, level: 'error' },
      error: null,
      isLoading: false,
      isFetching: false,
      isFetchedAfterMount: true,
      dataUpdatedAt: 1234,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof import('~/hooks').useLGQuery>;
    useFormState.setState({ submissionId: 's2' } as never);
    renderResult({});
    expect(recordSpy).not.toHaveBeenCalled();
  });
});

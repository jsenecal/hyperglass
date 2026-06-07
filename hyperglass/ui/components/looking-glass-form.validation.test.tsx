/**
 * Tests the form validation path: the vest suite wired through our
 * vestResolver (~/util/vest-resolver) must block submission and surface the
 * configured error messages when fields are missing.  These live in a
 * separate file so vi.mock hoisting does not conflict with the mocks in the
 * other looking-glass-form test files.
 */

import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// jsdom does not implement window.matchMedia; Chakra UI requires it.
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

import type { Config } from '~/types';
import { LookingGlassForm } from './looking-glass-form';

// ---------------------------------------------------------------------------
// next/router mock — query params are mutable so each test controls which
// fields are pre-filled.
// ---------------------------------------------------------------------------
let mockRouterQuery: Record<string, string> = {};

vi.mock('next/router', () => ({
  useRouter: () => ({
    query: mockRouterQuery,
    isReady: true,
    push: vi.fn(),
    replace: vi.fn(),
  }),
}));

// ---------------------------------------------------------------------------
// Minimal device + directive matching the query params above
// ---------------------------------------------------------------------------
const mockDirective = {
  id: 'juniper_bgp_route',
  name: 'BGP Route',
  fieldType: 'text',
  description: 'IP prefix / host',
  groups: [],
  info: null,
};

const mockDevice = {
  id: 'test1',
  name: 'Test Router 1',
  group: null,
  avatar: null,
  description: null,
  directives: [mockDirective],
};

const mockConfig: Config = {
  developerMode: false,
  primaryAsn: '65000',
  requestTimeout: 30,
  orgName: 'Test Org',
  siteTitle: 'hyperglass',
  siteDescription: 'Looking Glass',
  version: '2.0.0',
  parsedDataFields: [],
  devices: [{ group: null, locations: [mockDevice] }],
  content: { credit: '', greeting: '' },
  messages: {
    noInput: '{field} is required.',
    featureNotEnabled: 'Feature not enabled.',
    invalidInput: 'Invalid input.',
    general: 'An error occurred.',
    requestTimeout: 'Request timed out.',
    connectionError: 'Connection error.',
    authenticationError: 'Authentication error.',
    noOutput: 'No output.',
  },
  cache: {
    showText: false,
    timeout: 600,
    shareEnabled: false,
    shareTimeout: 604800,
    refreshMinInterval: 120,
  },
  web: {
    credit: { enable: false },
    dnsProvider: { name: 'Cloudflare', url: 'https://cloudflare-dns.com/dns-query' },
    links: [],
    menus: [],
    greeting: {
      enable: false,
      title: 'Welcome',
      button: 'Continue',
      required: false,
    },
    logo: {
      width: '100%',
      height: null,
      lightFormat: 'png',
      darkFormat: 'png',
    },
    text: {
      titleMode: 'logo',
      title: 'hyperglass',
      subtitle: 'Looking Glass',
      queryLocation: 'Location',
      queryType: 'Query Type',
      queryTarget: 'Query Target',
      fqdnTooltip: 'Resolve hostname',
      fqdnMessage: 'Resolving hostname',
      fqdnError: 'Could not resolve hostname',
      fqdnErrorButton: 'Try Again',
      cachePrefix: 'Cached',
      cacheIcon: '',
      completeTime: 'Completed in {time}',
      rpkiInvalid: 'INVALID',
      rpkiValid: 'VALID',
      rpkiUnknown: 'UNKNOWN',
      rpkiUnverified: 'UNVERIFIED',
      noCommunities: 'No communities',
      ipError: 'IP address error',
      noIp: 'No IP address detected',
      ipSelect: 'Select IP address',
      ipButton: 'Use My IP',
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
      refreshCooldown: 'Wait {seconds}s',
      requeryTooltip: 'Reload Query',
    },
    theme: {
      colors: { primary: '#40C057' },
      defaultColorMode: 'light',
      fonts: { body: 'Inter', mono: 'Fira Mono' },
    },
    locationDisplayMode: 'gallery',
    highlight: [],
  },
} as unknown as Config;

// ---------------------------------------------------------------------------
// ~/context mock
// ---------------------------------------------------------------------------
vi.mock('~/context', async () => {
  const { QueryClient } =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    useConfig: () => mockConfig,
    queryClient: new QueryClient(),
  };
});

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------
const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ChakraProvider>{children}</ChakraProvider>
    </QueryClientProvider>
  );
};

// ---------------------------------------------------------------------------
// Reset form state and mark the greeting acknowledged before each test, so
// validation is the only thing standing between a submit and submitHandler.
// ---------------------------------------------------------------------------
beforeEach(async () => {
  const { useFormState } = await import('~/hooks');
  const { useGreeting } = await import('~/hooks/use-greeting');
  await act(async () => {
    await useFormState.getState().reset();
    useGreeting.setState({ isAck: true, greetingReady: true, isOpen: false });
  });
});

describe('LookingGlassForm — vest validation blocks invalid submissions', () => {
  it('shows the configured message and does not submit when queryTarget is empty', async () => {
    const { useFormState } = await import('~/hooks');

    // Location and type pre-filled; target left empty.
    mockRouterQuery = { location: 'test1', type: 'juniper_bgp_route' };

    const { container } = render(<LookingGlassForm />, { wrapper });

    // Wait for the prefill effect — the directive-driven target field is the sentinel.
    await screen.findByPlaceholderText('IP prefix / host');

    fireEvent.submit(container.querySelector('form')!);

    // messages.noInput ('{field} is required.') interpolated with web.text.queryTarget.
    expect(await screen.findByText('Query Target is required.')).toBeInTheDocument();

    // submitHandler stamps a submissionId on every run — null proves it never ran.
    expect(useFormState.getState().submissionId).toBeNull();
  });

  it('shows the configured message and does not submit when the form is empty', async () => {
    const { useFormState } = await import('~/hooks');

    mockRouterQuery = {};

    const { container } = render(<LookingGlassForm />, { wrapper });

    fireEvent.submit(container.querySelector('form')!);

    expect(await screen.findByText('Location is required.')).toBeInTheDocument();
    expect(useFormState.getState().submissionId).toBeNull();
  });

  it('submits when all fields are valid', async () => {
    const { useFormState } = await import('~/hooks');

    mockRouterQuery = { location: 'test1', type: 'juniper_bgp_route', target: '192.0.2.0/24' };

    const { container } = render(<LookingGlassForm />, { wrapper });
    await screen.findAllByDisplayValue('192.0.2.0/24');

    fireEvent.submit(container.querySelector('form')!);

    // The vest suite passed: submitHandler ran and stamped a submissionId.
    await vi.waitFor(() => {
      expect(useFormState.getState().submissionId).toBeTruthy();
    });

    // And no validation error is shown.
    expect(screen.queryByText('Query Target is required.')).not.toBeInTheDocument();
  });
});

/**
 * Tests that submitHandler stamps a fresh submissionId into form state on each
 * submit.  These live in a separate file so vi.mock hoisting does not conflict
 * with the prefill-focused mocks in looking-glass-form.test.tsx.
 */

import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
// next/router mock — form pre-fill params so the submit button appears
// ---------------------------------------------------------------------------
vi.mock('next/router', () => ({
  useRouter: () => ({
    query: {
      location: 'test1',
      target: '192.0.2.0/24',
      type: 'juniper_bgp_route',
    },
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
// Reset both form state and greeting state before each test.
// ---------------------------------------------------------------------------
beforeEach(async () => {
  const { useFormState } = await import('~/hooks');
  const { useGreeting } = await import('~/hooks/use-greeting');
  await act(async () => {
    await useFormState.getState().reset();
    // Reset greeting to un-acknowledged so each test starts clean.
    useGreeting.setState({ isAck: false, greetingReady: false, isOpen: false });
  });
});

describe('LookingGlassForm — submissionId stamped on submit', () => {
  it('sets a non-null submissionId in form state after a valid submit', async () => {
    const { useFormState } = await import('~/hooks');
    const { useGreeting } = await import('~/hooks/use-greeting');

    // Mark greeting as acknowledged so submitHandler does not bail out.
    act(() => {
      useGreeting.setState({ isAck: true, greetingReady: true, isOpen: false });
    });

    render(<LookingGlassForm />, { wrapper });

    // Wait for the prefill useEffect to fire — the target display value is the sentinel.
    await screen.findAllByDisplayValue('192.0.2.0/24');

    // Confirm submissionId is still null before submit.
    expect(useFormState.getState().submissionId).toBeNull();

    // Submit the form by clicking the submit button.
    const submitBtn = screen.getByRole('button', { name: /submit query/i });
    await userEvent.click(submitBtn);

    // submitHandler should have called setSubmissionId(makeSubmissionId()).
    expect(useFormState.getState().submissionId).toBeTruthy();
  });

  it('stamps a new submissionId on each submit (not reusing the previous value)', async () => {
    const { useFormState } = await import('~/hooks');
    const { useGreeting } = await import('~/hooks/use-greeting');

    act(() => {
      useGreeting.setState({ isAck: true, greetingReady: true, isOpen: false });
    });

    render(<LookingGlassForm />, { wrapper });
    await screen.findAllByDisplayValue('192.0.2.0/24');

    const submitBtn = screen.getByRole('button', { name: /submit query/i });

    // First submit.
    await userEvent.click(submitBtn);
    const firstId = useFormState.getState().submissionId;
    expect(firstId).toBeTruthy();

    // Reset back to form view so the button is still accessible.
    act(() => {
      useFormState.getState().setStatus('form');
    });

    // Second submit.
    await userEvent.click(submitBtn);
    const secondId = useFormState.getState().submissionId;
    expect(secondId).toBeTruthy();
    expect(secondId).not.toBe(firstId);
  });
});

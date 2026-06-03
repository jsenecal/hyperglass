import { ChakraProvider } from '@chakra-ui/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
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
// next/router mock — query params that should pre-fill the form
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
// Minimal device + directive that matches the three query params above
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
// ~/context mock — provide config + the queryClient used by useFormState
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
// Wrapper: ChakraProvider only (QueryClientProvider is inside HyperglassProvider
// but since we mock ~/context we provide our own here)
// ---------------------------------------------------------------------------
const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ChakraProvider>{children}</ChakraProvider>
    </QueryClientProvider>
  );
};

// Reset Zustand form state between tests so pre-fill useEffect fires cleanly
beforeEach(async () => {
  const { useFormState } = await import('~/hooks');
  await useFormState.getState().reset();
});

describe('LookingGlassForm — query-string pre-fill', () => {
  it('pre-fills queryTarget display value from ?target= query param', async () => {
    render(<LookingGlassForm />, { wrapper });
    // QueryTarget renders an <Input> (name="queryTargetDisplay") whose displayed value is
    // s.target.display from Zustand. After the useEffect fires it should equal the ?target= param.
    // Multiple inputs carry this value (hidden RHF input + visible Input), so use getAllBy.
    const inputs = await screen.findAllByDisplayValue('192.0.2.0/24');
    expect(inputs.length).toBeGreaterThan(0);
    // The visible user-facing input has name="queryTargetDisplay"
    const visibleInput = inputs.find(el => el.getAttribute('name') === 'queryTargetDisplay');
    expect(visibleInput).toBeInTheDocument();
  });

  it('pre-fills queryLocation in Zustand form state from ?location= query param', async () => {
    const { useFormState } = await import('~/hooks');
    render(<LookingGlassForm />, { wrapper });
    // Wait for the target pre-fill to confirm the effect has run.
    await screen.findAllByDisplayValue('192.0.2.0/24');
    // Then verify queryLocation was set in Zustand form state.
    expect(useFormState.getState().form.queryLocation).toContain('test1');
    // Also verify selections.queryLocation was populated with the matching option object so that
    // the dropdown <Select value=...> and gallery LocationCard both reflect the pre-filled value.
    const locationSelections = useFormState.getState().selections.queryLocation;
    expect(locationSelections).toHaveLength(1);
    expect(locationSelections[0]).toMatchObject({ value: 'test1', label: 'Test Router 1' });
  });

  it('gallery LocationCard reflects checked state after pre-fill', async () => {
    const { container } = render(<LookingGlassForm />, { wrapper });
    // Wait for the pre-fill effect to fire (target field is the reliable sentinel).
    await screen.findAllByDisplayValue('192.0.2.0/24');
    // LocationCard exposes data-checked="true" on the wrapper div when isChecked is true.
    // After pre-fill, the card for "Test Router 1" (id=test1) should be marked checked.
    const checkedCard = container.querySelector('[data-checked="true"]');
    expect(checkedCard).toBeInTheDocument();
    // Confirm it is the card for the correct location by checking it contains the device name.
    expect(checkedCard?.textContent).toContain('Test Router 1');
  });
});

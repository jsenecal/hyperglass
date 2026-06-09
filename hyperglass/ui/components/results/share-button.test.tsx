import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Config } from '~/types';
import { ShareButton } from './share-button';

// Mutable config object so individual tests can override shareEnabled.
let mockConfig: Config;

vi.mock('~/context', () => ({
  useConfig: () => mockConfig,
}));

const buildConfig = (overrides: Partial<Config> = {}): Config =>
  ({
    cache: {
      timeout: 600,
      shareEnabled: true,
      shareTimeout: 604800,
      refreshMinInterval: 120,
      showText: false,
    },
    web: {
      text: {
        shareButton: 'Share',
        sharePopoverTitle: 'Share this result',
        shareCopyLink: 'Copy link',
        shareLinkCopied: 'Copied!',
        shareExpiresAt: 'Expires {expires}',
        shareCreateError: 'Could not create share link.',
        shareCreateExpired: 'Result expired. Refresh and try again.',
      },
    },
    ...overrides,
  }) as unknown as Config;

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
};

const mockResponse = (overrides: Partial<Response>) =>
  ({
    ok: true,
    status: 200,
    json: async () => ({}),
    text: async () => '',
    ...overrides,
  }) as unknown as Response;

beforeEach(() => {
  mockConfig = buildConfig();
  global.fetch = vi.fn();
});

describe('ShareButton', () => {
  it('hides itself when shareEnabled is false', () => {
    mockConfig = buildConfig({
      cache: {
        timeout: 600,
        shareEnabled: false,
        shareTimeout: 604800,
        refreshMinInterval: 120,
        showText: false,
      },
    } as unknown as Partial<Config>);

    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper });
    expect(screen.queryByRole('button', { name: /Share/i })).toBeNull();
  });

  it('renders with the configured shareButton text', () => {
    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper });
    expect(screen.getByRole('button', { name: /Share/i })).toBeInTheDocument();
  });

  it('POSTs the cacheId on click and shows the popover', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({
        json: async () => ({
          id: 'aaaaaaaaaaa',
          url: 'https://x/result/aaaaaaaaaaa',
          expiresAt: '2026-05-08T00:00:00Z',
        }),
      }),
    );

    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper });
    fireEvent.click(screen.getByRole('button', { name: /Share/i }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/query/share/hyperglass.query.deadbeef',
        expect.objectContaining({ method: 'POST' }),
      ),
    );

    await waitFor(() => expect(screen.getByText('Copy link')).toBeInTheDocument());
  });

  it('copies URL to clipboard on copy click', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({
        json: async () => ({
          id: 'aaaaaaaaaaa',
          url: 'https://x/result/aaaaaaaaaaa',
          expiresAt: '2026-05-08T00:00:00Z',
        }),
      }),
    );

    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper });
    fireEvent.click(screen.getByRole('button', { name: /Share/i }));

    await waitFor(() => expect(screen.getByText('Copy link')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Copy link'));
    expect(writeText).toHaveBeenCalledWith('https://x/result/aaaaaaaaaaa');
  });

  it('shows configured shareCreateExpired text on 410', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({ ok: false, status: 410, text: async () => 'Gone' }),
    );

    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper });
    fireEvent.click(screen.getByRole('button', { name: /Share/i }));

    await waitFor(() =>
      expect(screen.getByText('Result expired. Refresh and try again.')).toBeInTheDocument(),
    );
  });

  it('calls onShared with the minted id on success', async () => {
    const onShared = vi.fn();

    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({
        json: async () => ({
          id: 'ABCDEFGHIJK',
          url: 'http://x/result/ABCDEFGHIJK',
          expiresAt: '2026-05-08T00:00:00Z',
        }),
      }),
    );

    render(<ShareButton cacheId="cache1" onShared={onShared} />, { wrapper });
    fireEvent.click(screen.getByRole('button', { name: /Share/i }));

    await waitFor(() => expect(onShared).toHaveBeenCalledWith('ABCDEFGHIJK'));
  });

  it('does not POST again when popover is closed and reopened', async () => {
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      mockResponse({
        json: async () => ({
          id: 'aaaaaaaaaaa',
          url: 'https://x/result/aaaaaaaaaaa',
          expiresAt: '2026-05-08T00:00:00Z',
        }),
      }),
    );

    render(<ShareButton cacheId="hyperglass.query.deadbeef" />, { wrapper });

    // First click — opens popover and fires mutation.
    fireEvent.click(screen.getByRole('button', { name: /Share/i }));
    await waitFor(() => expect(screen.getByText('Copy link')).toBeInTheDocument());

    // Close the popover via the close button.
    fireEvent.click(screen.getByLabelText('Close'));

    // Second click — should reuse cached result, no new POST.
    fireEvent.click(screen.getByRole('button', { name: /Share/i }));
    await waitFor(() => expect(screen.getByText('Copy link')).toBeInTheDocument());

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});

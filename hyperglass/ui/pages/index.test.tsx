import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const push = vi.fn();
vi.mock('next/router', () => ({ useRouter: () => ({ push }) }));

// Stub heavy/dynamic children so the test isolates URL behavior.
vi.mock('~/components/results/snapshot-results', () => ({ SnapshotResults: () => null }));
vi.mock('~/elements', () => ({ FloatingBackButton: () => null, Loading: () => null }));
vi.mock('next/dynamic', () => ({ default: () => () => null }));

// biome-ignore lint/suspicious/noExplicitAny: test mock state, type is intentionally loose
let mockState: any;
vi.mock('~/hooks', () => ({
  useView: () => 'form',
  // biome-ignore lint/suspicious/noExplicitAny: test mock selector, mirrors Zustand selector signature
  useQueryHistory: (sel: any) => sel(mockState),
}));
vi.mock('~/context', () => ({ useConfig: () => ({ web: { text: { historyBack: 'Back' } } }) }));

import Index from './index';

const entry = {
  id: 'e1',
  savedAt: 0,
  query: { queryLocation: ['test1'], queryType: 'juniper_bgp_route', queryTarget: ['192.0.2.0/24'] },
  labels: { locations: ['Test1'], type: 'BGP Route', target: '192.0.2.0/24' },
  results: { test1: { id: 'c1' } },
};

beforeEach(() => {
  push.mockClear();
  mockState = { openId: 'e1', close: vi.fn(), entries: [entry] };
});

describe('Index opened-entry URL sync', () => {
  it('opening an un-shared entry shallow-pushes the deep-link', async () => {
    render(<Index />);
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        '/?location=test1&type=juniper_bgp_route&target=192.0.2.0%2F24',
        undefined,
        { shallow: true },
      ),
    );
  });

  it('opening a shared entry navigates to /result/<shareId>', async () => {
    mockState = { openId: 'e1', close: vi.fn(), entries: [{ ...entry, shareId: 'ABCDEFGHIJK' }] };
    render(<Index />);
    await waitFor(() => expect(push).toHaveBeenCalledWith('/result/ABCDEFGHIJK'));
  });
});

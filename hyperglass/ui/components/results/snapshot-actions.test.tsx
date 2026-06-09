import { ChakraProvider } from '@chakra-ui/react';
import { fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { describe, expect, it, vi } from 'vitest';

const push = vi.fn();
vi.mock('next/router', () => ({ useRouter: () => ({ push }) }));
vi.mock('~/context', () => ({
  useConfig: () => ({
    web: { text: { historyRerun: 'Run again', historyNewTarget: 'Run with a new target' } },
  }),
}));

import { SnapshotActions } from './snapshot-actions';

const q = { queryLocation: 'test1', queryType: 'juniper_bgp_route', queryTarget: '192.0.2.0/24' };

const renderActions = () =>
  render(
    <ChakraProvider>
      <SnapshotActions query={q} />
    </ChakraProvider>,
  );

describe('SnapshotActions', () => {
  it('Re-run navigates home with prefill + run flag', () => {
    renderActions();
    fireEvent.click(screen.getByLabelText('Run again'));
    expect(push).toHaveBeenCalledWith(
      '/?location=test1&type=juniper_bgp_route&target=192.0.2.0%2F24&run=1',
    );
  });

  it('New target navigates home with prefill, no run flag and no target', () => {
    renderActions();
    fireEvent.click(screen.getByLabelText('Run with a new target'));
    expect(push).toHaveBeenCalledWith('/?location=test1&type=juniper_bgp_route');
  });
});

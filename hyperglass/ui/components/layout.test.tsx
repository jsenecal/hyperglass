import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';
import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useFormState } from '~/hooks';

import type { Config } from '~/types';

// Layout pulls its actions from useFormState through a useShallow-wrapped
// object selector. With zustand v5, an unmemoized object-returning selector
// throws "Maximum update depth exceeded" at render time, so simply rendering
// Layout guards against that regression. Child components are stubbed — the
// store wiring is what's under test here, not the page chrome.
vi.mock('~/components', () => ({
  Debugger: () => <div data-testid="debugger" />,
  Footer: () => <div data-testid="footer" />,
  Greeting: () => <div data-testid="greeting" />,
  Header: () => <div data-testid="header" />,
  ResetButton: ({ resetForm }: { resetForm: () => void }) => (
    <button data-testid="reset" type="button" onClick={resetForm}>
      Reset
    </button>
  ),
}));

vi.mock('~/context', () => ({
  useConfig: () => ({ developerMode: false }) as Config,
  // use-form-state's reset() clears react-query caches via this export.
  queryClient: { removeQueries: vi.fn() },
}));

import { Layout } from './layout';

describe('Layout', () => {
  it('renders without a selector loop and resets form state', async () => {
    act(() => {
      useFormState.getState().setStatus('results');
    });

    render(
      <ChakraProvider>
        <Layout>
          <div data-testid="child" />
        </Layout>
      </ChakraProvider>,
    );

    expect(screen.getByTestId('child')).toBeInTheDocument();
    expect(screen.getByTestId('header')).toBeInTheDocument();
    expect(screen.getByTestId('footer')).toBeInTheDocument();

    // scrollIntoView is not implemented in jsdom.
    Element.prototype.scrollIntoView = vi.fn();
    await act(async () => {
      screen.getByTestId('reset').click();
    });
    expect(useFormState.getState().status).toBe('form');
  });
});

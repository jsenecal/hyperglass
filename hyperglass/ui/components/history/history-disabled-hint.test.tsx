import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

const cfg = vi.hoisted(() => ({ historyEnabled: true }));

vi.mock('~/context', () => ({
  useConfig: () => ({
    cache: { historyEnabled: cfg.historyEnabled },
    web: { text: { historyDisabledHint: 'Results for this query type are not saved to history.' } },
  }),
}));

import { HistoryDisabledHint } from './history-disabled-hint';

const renderHint = (directiveHistory: boolean) =>
  render(
    <ChakraProvider>
      <HistoryDisabledHint directiveHistory={directiveHistory} />
    </ChakraProvider>,
  );

describe('HistoryDisabledHint', () => {
  beforeEach(() => {
    cfg.historyEnabled = true;
  });

  it('renders when global history on and directive opts out', () => {
    renderHint(false);
    expect(screen.getByLabelText(/not saved to history/i)).toBeInTheDocument();
  });

  it('renders nothing when the directive allows history', () => {
    renderHint(true);
    expect(screen.queryByLabelText(/not saved to history/i)).not.toBeInTheDocument();
  });

  it('renders nothing when global history is disabled', () => {
    cfg.historyEnabled = false;
    renderHint(false);
    expect(screen.queryByLabelText(/not saved to history/i)).not.toBeInTheDocument();
  });
});

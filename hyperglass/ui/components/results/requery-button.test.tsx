import '@testing-library/jest-dom';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RequeryButton } from './requery-button';

// Provide minimal config satisfying RequeryButton's useConfig() call.
vi.mock('~/context', () => ({
  useConfig: () => ({
    cache: { timeout: 600, refreshMinInterval: 5 },
    web: { text: { refreshCooldown: 'Wait {seconds}s', requeryTooltip: 'Reload Query' } },
  }),
}));

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('RequeryButton', () => {
  it('is disabled until refreshMinInterval elapses (since lastResponseAt)', () => {
    const onRequery = vi.fn();
    const lastResponseAt = Date.now();

    render(
      <RequeryButton onRequery={onRequery} lastResponseAt={lastResponseAt} isDisabled={false} />,
    );
    const btn = screen.getByRole('button', { name: /Reload Query/i });
    expect(btn).toBeDisabled();

    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(btn).toBeEnabled();
  });

  it('calls onRequery on click after cooldown', () => {
    const onRequery = vi.fn();
    // Already past cooldown: lastResponseAt is 10 seconds ago
    const lastResponseAt = Date.now() - 10_000;

    render(
      <RequeryButton onRequery={onRequery} lastResponseAt={lastResponseAt} isDisabled={false} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Reload Query/i }));
    expect(onRequery).toHaveBeenCalledTimes(1);
  });

  it('does not call onRequery when clicked during cooldown', () => {
    const onRequery = vi.fn();
    // Still within cooldown: lastResponseAt is now
    const lastResponseAt = Date.now();

    render(
      <RequeryButton onRequery={onRequery} lastResponseAt={lastResponseAt} isDisabled={false} />,
    );
    const btn = screen.getByRole('button', { name: /Reload Query/i });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onRequery).not.toHaveBeenCalled();
  });
});

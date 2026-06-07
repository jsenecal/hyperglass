/**
 * Covers the GroupFilter radio buttons rendered inside QueryType's select
 * menu. GroupFilter destructures a prop getter from chakra's useRadio whose
 * name changed in chakra 2.9 (getCheckboxProps → getRadioProps); these tests
 * exercise that path end-to-end so the wiring can't silently regress.
 */

import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormProvider, useForm } from 'react-hook-form';
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

import type { Config, Directive } from '~/types';
import { QueryType } from './query-type';

vi.mock('~/context', () => ({
  useConfig: () => ({ web: { theme: { colors: {} } } }) as unknown as Config,
}));

const directive = (id: string, name: string, groups: string[]): Directive =>
  ({
    id,
    name,
    groups,
    fieldType: 'text',
    description: '',
    info: null,
  }) as unknown as Directive;

const Wrapper = ({ children }: { children: React.ReactNode }) => {
  const methods = useForm();
  return (
    <ChakraProvider>
      <FormProvider {...methods}>{children}</FormProvider>
    </ChakraProvider>
  );
};

beforeEach(async () => {
  const { useFormState } = await import('~/hooks');
  await act(async () => {
    await useFormState.getState().reset();
    useFormState.setState({
      filtered: {
        groups: ['IPv4', 'IPv6'],
        types: [
          directive('bgp_route_4', 'BGP Route (v4)', ['IPv4']),
          directive('bgp_route_6', 'BGP Route (v6)', ['IPv6']),
        ],
      },
    });
  });
});

describe('QueryType — GroupFilter radios', () => {
  // The chakra Button getRadioProps() decorates is aria-hidden and the radio
  // <input> it wires up is visually-hidden with no a11y name, so role queries
  // can't reach the GroupFilters — query the radio inputs from the DOM by value.
  const radios = () =>
    Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input[type="radio"][name="queryGroup"]'),
    );

  it('renders a group filter radio per configured group plus None', async () => {
    render(<QueryType onChange={vi.fn()} label="Query Type" />, {
      wrapper: Wrapper,
    });

    // Open the react-select menu, which renders the custom MenuList + GroupFilters.
    await userEvent.click(screen.getByLabelText('Query Type'));
    await screen.findByText('None');

    expect(radios().map(r => r.value)).toEqual(['', 'IPv4', 'IPv6']);
    // None is selected by default.
    expect(radios().find(r => r.value === '')).toBeChecked();
  });

  it('selecting a group filter narrows the visible options', async () => {
    render(<QueryType onChange={vi.fn()} label="Query Type" />, {
      wrapper: Wrapper,
    });

    await userEvent.click(screen.getByLabelText('Query Type'));

    // Both directives visible before filtering.
    expect(await screen.findByText('BGP Route (v4)')).toBeInTheDocument();
    expect(screen.getByText('BGP Route (v6)')).toBeInTheDocument();

    // getRadioProps wires the onClick onto the visible Button (the radio input
    // only carries checked state), so click the button as a user would — its
    // sibling within the GroupFilter label. This is the wiring under test:
    // selecting a group drives the option filter (only IPv6 directives remain).
    const ipv6 = radios().find(r => r.value === 'IPv6');
    await userEvent.click(ipv6?.nextElementSibling as HTMLElement);

    expect(await screen.findByText('BGP Route (v6)')).toBeInTheDocument();
    expect(screen.queryByText('BGP Route (v4)')).not.toBeInTheDocument();
  });
});

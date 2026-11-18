import { ChakraProvider } from '@chakra-ui/react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LossField } from './traceroute-fields';

describe('LossField', () => {
  it('supports missing and numeric loss values across requeries', () => {
    const field = (loss: number | null) => (
      <ChakraProvider>
        <LossField loss={loss} />
      </ChakraProvider>
    );
    const { rerender } = render(field(null));
    expect(screen.getByText('—')).toBeInTheDocument();
    rerender(field(25));
    expect(screen.getByText('25%')).toBeInTheDocument();
    rerender(field(null));
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});

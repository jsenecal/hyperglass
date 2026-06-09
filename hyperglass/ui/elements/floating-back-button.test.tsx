import { ChakraProvider } from '@chakra-ui/react';
import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FloatingBackButton } from './floating-back-button';

const renderEl = (props: Partial<React.ComponentProps<typeof FloatingBackButton>>) =>
  render(
    <ChakraProvider>
      <FloatingBackButton isVisible onClick={() => {}} label="Back" {...props} />
    </ChakraProvider>,
  );

describe('FloatingBackButton', () => {
  it('renders when visible and fires onClick', () => {
    const onClick = vi.fn();
    renderEl({ onClick });
    fireEvent.click(screen.getByLabelText('Back'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not render the button when not visible', () => {
    renderEl({ isVisible: false });
    expect(screen.queryByLabelText('Back')).not.toBeInTheDocument();
  });
});

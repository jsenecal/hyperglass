import { Flex, IconButton } from '@chakra-ui/react';
import { AnimatePresence } from 'framer-motion';
import { AnimatedDiv } from '~/elements/animated';
import { DynamicIcon } from '~/elements/dynamic-icon';
import { useColorValue, useOpposingColor } from '~/hooks';

import type { FlexProps } from '@chakra-ui/react';

interface FloatingBackButtonProps extends FlexProps {
  isVisible: boolean;
  onClick(): void;
  label: string;
  /** Extra bottom offset (e.g. developer-mode bar). */
  raised?: boolean;
}

export const FloatingBackButton = (props: FloatingBackButtonProps): JSX.Element => {
  const { isVisible, onClick, label, raised = false, ...rest } = props;
  const bg = useColorValue('primary.500', 'primary.300');
  const color = useOpposingColor(bg);
  return (
    <AnimatePresence>
      {isVisible && (
        <AnimatedDiv
          bg={bg}
          left={0}
          zIndex={4}
          bottom={24}
          boxSize={12}
          color={color}
          position="fixed"
          animate={{ x: 0 }}
          exit={{ x: '-100%' }}
          borderRightRadius="md"
          initial={{ x: '-100%' }}
          mb={raised ? { base: 0, lg: 14 } : undefined}
          transition={{ duration: 0.15, ease: [0.4, 0, 0.2, 1] }}
        >
          <Flex boxSize="100%" justifyContent="center" alignItems="center" {...rest}>
            <IconButton
              lineHeight={0}
              color="current"
              variant="unstyled"
              aria-label={label}
              onClick={onClick}
              icon={<DynamicIcon icon={{ fa: 'FaAngleLeft' }} boxSize={8} />}
            />
          </Flex>
        </AnimatedDiv>
      )}
    </AnimatePresence>
  );
};

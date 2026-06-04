import { Box, Tooltip } from '@chakra-ui/react';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';

interface HistoryDisabledHintProps {
  directiveHistory: boolean;
}

export const HistoryDisabledHint = (props: HistoryDisabledHintProps): JSX.Element | null => {
  const { directiveHistory } = props;
  const { cache, web } = useConfig();

  if (!cache.historyEnabled || directiveHistory) {
    return null;
  }

  return (
    <Tooltip hasArrow label={web.text.historyDisabledHint} placement="top">
      <Box as="span" aria-label={web.text.historyDisabledHint} display="inline-flex">
        <DynamicIcon icon={{ fi: 'FiEyeOff' }} boxSize="14px" />
      </Box>
    </Tooltip>
  );
};

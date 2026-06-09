import { Button, HStack, Tooltip } from '@chakra-ui/react';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';
import { usePrefillNavigate } from '~/hooks';

export interface SnapshotActionsProps {
  query: { queryLocation: string; queryType: string; queryTarget: string };
}

const iconBtn = {
  mx: 1,
  size: 'sm' as const,
  variant: 'ghost' as const,
  colorScheme: 'secondary' as const,
};

export const SnapshotActions = (props: SnapshotActionsProps): JSX.Element => {
  const { query } = props;
  const { web } = useConfig();
  const navigate = usePrefillNavigate();

  return (
    <HStack spacing={0} flex="0 0 auto">
      <Tooltip hasArrow label={web.text.historyRerun} placement="top">
        <Button
          {...iconBtn}
          aria-label={web.text.historyRerun}
          onClick={() =>
            navigate(
              {
                queryLocation: query.queryLocation,
                queryType: query.queryType,
                queryTarget: query.queryTarget,
              },
              { run: true },
            )
          }
        >
          <DynamicIcon icon={{ fi: 'FiRepeat' }} boxSize="16px" />
        </Button>
      </Tooltip>
      <Tooltip hasArrow label={web.text.historyNewTarget} placement="top">
        <Button
          {...iconBtn}
          aria-label={web.text.historyNewTarget}
          onClick={() =>
            navigate({ queryLocation: query.queryLocation, queryType: query.queryType })
          }
        >
          <DynamicIcon icon={{ fi: 'FiEdit' }} boxSize="16px" />
        </Button>
      </Tooltip>
    </HStack>
  );
};

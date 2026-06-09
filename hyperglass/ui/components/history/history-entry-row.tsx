import { Button, Flex, HStack, Text, Tooltip, useToast } from '@chakra-ui/react';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { ShareButton } from '~/components/results/share-button';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';
import { useDevice, useFormState, useQueryHistory } from '~/hooks';
import { makeSubmissionId } from '~/util';

import type { HistoryEntry } from '~/hooks/use-query-history';

dayjs.extend(relativeTime);

interface HistoryEntryRowProps {
  entry: HistoryEntry;
}

const iconBtn = {
  as: 'a' as const,
  mx: 1,
  size: 'sm' as const,
  variant: 'ghost' as const,
  colorScheme: 'secondary' as const,
};

export const HistoryEntryRow = (props: HistoryEntryRowProps): JSX.Element => {
  const { entry } = props;
  const { web, messages } = useConfig();
  const toast = useToast();
  const getDevice = useDevice();

  const open = useQueryHistory(s => s.open);
  const remove = useQueryHistory(s => s.remove);
  const setShareId = useQueryHistory(s => s.setShareId);
  const prefillForm = useFormState(s => s.prefillForm);
  const setStatus = useFormState(s => s.setStatus);
  const setSubmissionId = useFormState(s => s.setSubmissionId);

  const deviceIds = Object.keys(entry.results);
  const isSingleDevice = deviceIds.length === 1;
  const hasOutput = deviceIds.some(id => 'output' in entry.results[id]);

  const failStale = () =>
    toast({ title: messages.historyDeviceUnavailable, status: 'error', isClosable: true });

  const handleRerun = () => {
    const valid = prefillForm(entry.query, getDevice);
    if (valid.length === 0) return failStale();
    setSubmissionId(makeSubmissionId());
    setStatus('results');
  };

  const handleNewTarget = () => {
    const valid = prefillForm({ ...entry.query, queryTarget: [] }, getDevice);
    if (valid.length === 0) return failStale();
    setStatus('form');
  };

  return (
    <Flex
      px={3}
      py={2}
      w="100%"
      align="center"
      justify="space-between"
      borderTopWidth="1px"
      _first={{ borderTopWidth: 0 }}
    >
      <Flex direction="column" textAlign="left" minW={0} mr={2}>
        <Text fontSize="sm" fontWeight="medium" isTruncated>
          {entry.labels.locations.join(', ')} · {entry.labels.type} · {entry.labels.target}
        </Text>
        <Text fontSize="xs" color="gray.500">
          {dayjs(entry.savedAt).fromNow()}
        </Text>
      </Flex>
      <HStack spacing={0} flex="0 0 auto">
        {hasOutput && (
          <Tooltip hasArrow label={web.text.historyOpen} placement="top">
            <Button {...iconBtn} aria-label={web.text.historyOpen} onClick={() => open(entry.id)}>
              <DynamicIcon icon={{ fi: 'FiEye' }} boxSize="16px" />
            </Button>
          </Tooltip>
        )}
        {isSingleDevice && (
          <ShareButton
            cacheId={entry.results[deviceIds[0]].id}
            onShared={shareId => setShareId(entry.id, shareId)}
          />
        )}
        <Tooltip hasArrow label={web.text.historyRerun} placement="top">
          <Button {...iconBtn} aria-label={web.text.historyRerun} onClick={handleRerun}>
            <DynamicIcon icon={{ fi: 'FiRepeat' }} boxSize="16px" />
          </Button>
        </Tooltip>
        <Tooltip hasArrow label={web.text.historyNewTarget} placement="top">
          <Button {...iconBtn} aria-label={web.text.historyNewTarget} onClick={handleNewTarget}>
            <DynamicIcon icon={{ fi: 'FiEdit' }} boxSize="16px" />
          </Button>
        </Tooltip>
        <Tooltip hasArrow label={web.text.historyDelete} placement="top">
          <Button
            {...iconBtn}
            aria-label={web.text.historyDelete}
            colorScheme="red"
            onClick={() => remove(entry.id)}
          >
            <DynamicIcon icon={{ fi: 'FiTrash2' }} boxSize="16px" />
          </Button>
        </Tooltip>
      </HStack>
    </Flex>
  );
};

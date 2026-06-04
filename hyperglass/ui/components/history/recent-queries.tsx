import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Box,
  Button,
  Flex,
  Text,
  useDisclosure,
} from '@chakra-ui/react';
import { useEffect, useRef, useState } from 'react';
import { useConfig } from '~/context';
import { useFormInteractive, useQueryHistory } from '~/hooks';
import { HistoryEntryRow } from './history-entry-row';

export const RecentQueries = (): JSX.Element | null => {
  const { cache, web } = useConfig();
  const formInteractive = useFormInteractive();
  const entries = useQueryHistory(s => s.entries);
  const clear = useQueryHistory(s => s.clear);

  // Render only after mount to avoid a next-export hydration mismatch
  // (server sees no localStorage; client rehydrates).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const { isOpen, onOpen, onClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  if (!mounted || !cache.historyEnabled || formInteractive || entries.length === 0) {
    return null;
  }

  return (
    <Box w="100%" maxW={{ base: '100%', lg: '75%' }} mx="auto" my={4} textAlign="left">
      <Flex px={3} py={2} align="center" justify="space-between">
        <Text fontSize="sm" fontWeight="bold" textTransform="uppercase" color="gray.500">
          {web.text.historyTitle}
        </Text>
        <Button size="xs" variant="ghost" colorScheme="red" onClick={onOpen}>
          {web.text.historyClearAll}
        </Button>
      </Flex>
      <Box borderWidth="1px" rounded="lg" overflow="hidden">
        {entries.map(entry => (
          <HistoryEntryRow key={entry.id} entry={entry} />
        ))}
      </Box>

      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader>{web.text.historyClearConfirm}</AlertDialogHeader>
            <AlertDialogBody />
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onClose}>
                {web.text.historyBack}
              </Button>
              <Button
                colorScheme="red"
                ml={3}
                onClick={() => {
                  clear();
                  onClose();
                }}
              >
                {web.text.historyClearAll}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
};

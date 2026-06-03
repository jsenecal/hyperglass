import {
  Button,
  HStack,
  Input,
  Popover,
  PopoverArrow,
  PopoverBody,
  PopoverCloseButton,
  PopoverContent,
  PopoverHeader,
  PopoverTrigger,
  Spinner,
  Text,
  VStack,
} from '@chakra-ui/react';
import { useEffect, useRef, useState } from 'react';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';
import { useShareCreate, useStrf } from '~/hooks';
import { ShareError } from '~/hooks/use-share';

export interface ShareButtonProps {
  cacheId: string;
}

export const ShareButton = (props: ShareButtonProps): JSX.Element | null => {
  const { cacheId } = props;

  const { cache, web } = useConfig();
  const strF = useStrf();
  const { mutate, data, error, isSuccess, isError, isLoading } = useShareCreate();

  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  // Track the reset timer so it can be cancelled on unmount (finding 1).
  const copiedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copiedTimerRef.current !== null) {
        clearTimeout(copiedTimerRef.current);
        copiedTimerRef.current = null;
      }
    };
  }, []);

  if (!cacheId || !cache.shareEnabled) {
    return null;
  }

  const handleShare = () => {
    // Only fire the mutation when there is no successful result yet (finding 2).
    if (!isSuccess) {
      mutate(cacheId);
    }
    setIsOpen(true);
  };

  const handleCopy = () => {
    if (data?.url) {
      navigator.clipboard.writeText(data.url);
      setCopied(true);
      if (copiedTimerRef.current !== null) {
        clearTimeout(copiedTimerRef.current);
      }
      copiedTimerRef.current = setTimeout(() => {
        setCopied(false);
        copiedTimerRef.current = null;
      }, 2000);
    }
  };

  const expiryText =
    isSuccess && data?.expiresAt
      ? strF(web.text.shareExpiresAt, { expires: new Date(data.expiresAt).toLocaleString() })
      : null;

  const errorText = isError
    ? (error as ShareError).status === 410
      ? web.text.shareCreateExpired
      : web.text.shareCreateError
    : null;

  return (
    <Popover isOpen={isOpen} onClose={() => setIsOpen(false)} placement="top">
      <PopoverTrigger>
        {/* aria-label removed: button has visible text (finding 4) */}
        <Button
          mx={1}
          size="sm"
          zIndex="1"
          variant="ghost"
          colorScheme="secondary"
          onClick={handleShare}
          isLoading={isLoading}
        >
          <DynamicIcon icon={{ fi: 'FiShare2' }} boxSize="16px" mr={1} />
          {web.text.shareButton}
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        <PopoverArrow />
        <PopoverCloseButton />
        <PopoverHeader fontWeight="semibold">{web.text.sharePopoverTitle}</PopoverHeader>
        <PopoverBody>
          {/* Show a spinner while the POST is in flight (finding 5) */}
          {isLoading && <Spinner size="sm" />}
          {isSuccess && data && (
            <VStack align="stretch" spacing={3}>
              {/* aria-label from config for accessible label on readonly input (finding 3) */}
              <Input
                value={data.url}
                isReadOnly
                size="sm"
                aria-label={web.text.sharePopoverTitle}
              />
              <HStack justify="space-between">
                <Button size="sm" colorScheme="primary" onClick={handleCopy}>
                  {copied ? web.text.shareLinkCopied : web.text.shareCopyLink}
                </Button>
                {expiryText && (
                  <Text fontSize="xs" color="gray.500">
                    {expiryText}
                  </Text>
                )}
              </HStack>
            </VStack>
          )}
          {errorText && (
            <Text color="red.500" fontSize="sm">
              {errorText}
            </Text>
          )}
        </PopoverBody>
      </PopoverContent>
    </Popover>
  );
};

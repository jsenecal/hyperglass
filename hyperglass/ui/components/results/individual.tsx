import {
  AccordionButton,
  AccordionItem,
  AccordionPanel,
  Alert,
  Box,
  Flex,
  HStack,
  Tooltip,
  chakra,
  useAccordionContext,
  useToast,
} from '@chakra-ui/react';
import { useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import startCase from 'lodash/startCase';
import { forwardRef, memo, useEffect, useMemo, useState } from 'react';
import isEqual from 'react-fast-compare';
import { Else, If, Then } from 'react-if';
import { BGPTable, Path, TextOutput } from '~/components';
import { HistoryDisabledHint } from '~/components/history/history-disabled-hint';
import { useConfig } from '~/context';
import { Countdown, DynamicIcon } from '~/elements';
import {
  useColorValue,
  useDevice,
  useFormState,
  useLGQuery,
  useMobile,
  useRecordHistory,
  useStrf,
  useTableToString,
} from '~/hooks';
import { isStringOutput, isStructuredOutput } from '~/types';
import { CopyButton } from './copy-button';
import { FormattedError } from './formatted-error';
import { isFetchError, isLGError, isLGOutputOrError, isStackError } from './guards';
import { ResultHeader } from './header';
import { RequeryButton } from './requery-button';
import { ShareButton } from './share-button';

import type { ErrorLevels } from '~/types';

interface ResultProps {
  index: number;
  queryLocation: string;
  /** Snapshot from a share link — skips the live LG query and renders directly. */
  snapshot?: ResultSnapshot;
  /** When true, hides the RequeryButton (used on the share view page). */
  readOnly?: boolean;
  /** Controls ShareButton visibility; defaults to !readOnly. */
  showShare?: boolean;
}

const AnimatedAccordionItem = motion(AccordionItem);

const AccordionHeaderWrapper = chakra('div', {
  baseStyle: {
    display: 'flex',
    justifyContent: 'space-between',
    _hover: { bg: 'blackAlpha.50' },
    _focus: { boxShadow: 'outline' },
  },
});

const _Result: React.ForwardRefRenderFunction<HTMLDivElement, ResultProps> = (
  props: ResultProps,
  ref,
) => {
  const { index, queryLocation, snapshot, readOnly = false, showShare = !readOnly } = props;
  const toast = useToast();
  const { web, cache, messages } = useConfig();
  const { index: indices, setIndex } = useAccordionContext();
  const getDevice = useDevice();
  const device = getDevice(queryLocation);

  const queryClient = useQueryClient();

  const isMobile = useMobile();
  const color = useColorValue('black', 'white');
  const scrollbar = useColorValue('blackAlpha.300', 'whiteAlpha.300');
  const scrollbarHover = useColorValue('blackAlpha.400', 'whiteAlpha.400');
  const scrollbarBg = useColorValue('blackAlpha.50', 'whiteAlpha.50');

  const addResponse = useFormState(s => s.addResponse);
  const form = useFormState(s => s.form);
  const recordHistory = useRecordHistory();
  const getDirective = useFormState(s => s.getDirective);
  const submissionId = useFormState(s => s.submissionId);
  const [errorLevel, _setErrorLevel] = useState<ErrorLevels>('error');
  const [force, setForce] = useState<true | undefined>(undefined);
  // Track when data last arrived for the cooldown gate. Initialise to mount
  // time so the button starts cooling-down from mount rather than from epoch 0.
  const [lastResponseAt, setLastResponseAt] = useState<number>(() => Date.now());

  const setErrorLevel = (level: ResponseLevel): void => {
    let e: ErrorLevels = 'error';
    switch (level) {
      case 'success':
        e = level;
        break;
      case 'warning' || 'error':
        e = 'warning';
        break;
    }
    _setErrorLevel(e);
  };

  // When snapshot is provided, coerce it to a QueryResponse shape so all
  // downstream rendering logic can remain unchanged.
  const snapshotAsQueryResponse: QueryResponse | undefined = useMemo(() => {
    if (!snapshot) return undefined;
    return {
      id: snapshot.id,
      random: '',
      cached: snapshot.cached,
      runtime: snapshot.runtime,
      level: snapshot.level,
      timestamp: snapshot.timestamp,
      keywords: snapshot.keywords,
      output: snapshot.output,
      format: snapshot.format as QueryResponse['format'],
    };
  }, [snapshot]);

  const {
    data: liveData,
    error,
    isLoading,
    isFetching,
    isFetchedAfterMount,
    dataUpdatedAt,
  } = useLGQuery(
    { queryLocation, queryTarget: form.queryTarget, queryType: form.queryType, force },
    {
      // Disable the live fetch when rendering from a snapshot.
      enabled: !snapshot,
      onSuccess(data) {
        if (device !== null) {
          addResponse(device.id, data);
        }
        if (isLGOutputOrError(data)) {
          console.error(data);
          setErrorLevel(data.level);
        }
      },
      onError(error) {
        console.error({ error });
        if (isLGOutputOrError(error)) {
          setErrorLevel(error.level);
        }
      },
    },
  );

  // In snapshot mode, use the coerced snapshot; otherwise use the live query result.
  const data = snapshot ? snapshotAsQueryResponse : liveData;

  // When a forced fetch settles, copy the fresh result into the non-force cache
  // key (K1) before resetting force back to undefined. Without this, reverting
  // the key from K2={…,force:true} to K1={…} causes React Query to serve K1's
  // stale data because refetchOnMount/refetchOnWindowFocus are both disabled.
  useEffect(() => {
    if (dataUpdatedAt > 0) {
      setLastResponseAt(dataUpdatedAt);
      if (force && data && !isFetching) {
        // Populate K1 with the fresh forced result so the UI keeps showing the
        // new data once force reverts to undefined and the key swaps back to K1.
        // React Query v4 hashes keys structurally and drops undefined values, so
        // omitting force entirely matches K1's stored entry.
        queryClient.setQueryData(
          [
            '/api/query',
            { queryLocation, queryTarget: form.queryTarget, queryType: form.queryType },
          ],
          data,
        );
        setForce(undefined);
      }
    }
    // force, data, queryLocation, form.queryTarget, form.queryType, and
    // queryClient are intentionally omitted: they are all stable within a settled
    // fetch cycle. Re-running on any of those would risk double-firing the
    // setQueryData / setForce(undefined) calls.
  }, [dataUpdatedAt, isFetching]); // eslint-disable-line react-hooks/exhaustive-deps

  // Record a successful result into query history. Keyed on dataUpdatedAt +
  // submissionId so it fires for both fresh and cache-served settles, once per
  // run. Skipped for snapshot/read-only renders. The global + per-directive
  // gates live inside useRecordHistory.
  useEffect(() => {
    if (snapshot || readOnly) return;
    if (data?.level === 'success' && submissionId && device !== null) {
      const directive = getDirective();
      recordHistory({
        submissionId,
        deviceId: device.id,
        deviceLabel: device.name,
        directiveHistory: directive?.history ?? true,
        query: { queryType: form.queryType, queryTarget: form.queryTarget },
        labels: { type: directive?.name ?? form.queryType, target: form.queryTarget.join(' ') },
        snapshot: {
          id: data.id,
          output: data.output,
          format: data.format,
          level: data.level,
          timestamp: data.timestamp,
          runtime: data.runtime,
          cached: data.cached,
          keywords: data.keywords ?? [],
          queryLabels: { location: device.name, type: directive?.name ?? form.queryType },
        },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataUpdatedAt, submissionId]);

  const isError = useMemo(() => isLGOutputOrError(data), [data, error]);

  const isCached = useMemo(() => data?.cached || !isFetchedAfterMount, [data, isFetchedAfterMount]);

  const strF = useStrf();
  const cacheLabel = strF(web.text.cacheIcon, { time: data?.timestamp });

  const errorKeywords = useMemo(() => {
    let kw = [] as string[];
    if (isLGError(data)) {
      kw = data.keywords;
    }
    return kw;
  }, [data]);

  // Parse the the response and/or the error to determine from where to extract the error message.
  const errorMsg = useMemo(() => {
    if (isLGError(error)) {
      return error.output as string;
    }
    if (isLGOutputOrError(data)) {
      return data.output as string;
    }
    if (isFetchError(error)) {
      return startCase(error.statusText);
    }
    if (isStackError(error) && error.message.toLowerCase().startsWith('timeout')) {
      return messages.requestTimeout;
    }
    if (isStackError(error)) {
      return startCase(error.message);
    }
    return messages.general;
  }, [error, data, messages.general, messages.requestTimeout]);

  const tableComponent = useMemo<boolean>(() => {
    let result = false;
    if (data?.format === 'application/json') {
      result = true;
    }
    return result;
  }, [data?.format]);

  let copyValue = data?.output as string;

  const formatData = useTableToString(form.queryTarget, data, [data?.format]);

  if (data?.format === 'application/json') {
    copyValue = formatData();
  }

  if (error) {
    copyValue = errorMsg;
  }

  // Signal to the group that this result is done loading.
  useEffect(() => {
    // Only set the index if it's not already set and the query is finished loading.
    if (Array.isArray(indices) && indices.length === 0 && !isLoading) {
      // Only set the index if the response has data or an error.
      if (data || isError) {
        setIndex([index]);
      }
    }
  }, [data, index, indices, isLoading, isError, setIndex]);

  // In snapshot mode, the device may not be in the config (share viewer may not
  // have the same device list). Fall back to snapshot labels for title/id.
  const deviceId = device?.id ?? queryLocation;
  const deviceName = device?.name ?? snapshot?.queryLabels.location ?? queryLocation;

  if (device === null && !snapshot) {
    const id = `toast-queryLocation-${index}-${queryLocation}`;
    if (!toast.isActive(id)) {
      toast({
        id,
        title: messages.general,
        description: `Configuration for device with ID '${queryLocation}' not found.`,
        status: 'error',
        isClosable: true,
      });
    }
    return <></>;
  }

  return (
    <AnimatedAccordionItem
      ref={ref}
      id={deviceId}
      isDisabled={!snapshot && isLoading}
      exit={{ opacity: 0, y: 300 }}
      animate={{ opacity: 1, y: 0 }}
      initial={{ opacity: 0, y: 300 }}
      transition={{ duration: 0.3, delay: index * 0.3 }}
      css={{
        '&:first-of-type': { borderTop: 'none' },
        '&:last-of-type': { borderBottom: 'none' },
      }}
    >
      <AccordionHeaderWrapper>
        <AccordionButton py={2} w="unset" _hover={{}} _focus={{}} flex="1 0 auto">
          <ResultHeader
            isError={isError}
            loading={!snapshot && isLoading}
            errorMsg={errorMsg}
            errorLevel={errorLevel}
            runtime={data?.runtime ?? 0}
            title={deviceName}
          />
        </AccordionButton>
        <HStack py={2} spacing={1}>
          {!snapshot && isStructuredOutput(data) && data.level === 'success' && tableComponent && (
            <Path device={deviceId} />
          )}
          {showShare && data?.id && <ShareButton cacheId={data.id} />}
          {!snapshot && <HistoryDisabledHint directiveHistory={getDirective()?.history ?? true} />}
          <CopyButton copyValue={copyValue} isDisabled={!snapshot && isLoading} />
          {!readOnly && (
            <RequeryButton
              onRequery={() => setForce(true)}
              lastResponseAt={lastResponseAt}
              isDisabled={isLoading}
            />
          )}
        </HStack>
      </AccordionHeaderWrapper>
      <AccordionPanel
        pb={4}
        overflowX="auto"
        css={{
          WebkitOverflowScrolling: 'touch',
          '&::-webkit-scrollbar': { height: '5px' },
          '&::-webkit-scrollbar-track': {
            backgroundColor: scrollbarBg,
          },
          '&::-webkit-scrollbar-thumb': {
            backgroundColor: scrollbar,
          },
          '&::-webkit-scrollbar-thumb:hover': {
            backgroundColor: scrollbarHover,
          },

          '-ms-overflow-style': { display: 'none' },
        }}
      >
        <Box>
          <Flex direction="column" flex="1 0 auto" maxW={error ? '100%' : undefined}>
            <If condition={!isError && typeof data !== 'undefined'}>
              <Then>
                {isStructuredOutput(data) && data.level === 'success' && tableComponent ? (
                  <BGPTable>{data.output}</BGPTable>
                ) : isStringOutput(data) && data.level === 'success' && !tableComponent ? (
                  <TextOutput>{data.output}</TextOutput>
                ) : isStringOutput(data) && data.level !== 'success' ? (
                  <Alert rounded="lg" my={2} py={4} status={errorLevel} variant="solid">
                    <FormattedError message={data.output} keywords={errorKeywords} />
                  </Alert>
                ) : (
                  <Alert rounded="lg" my={2} py={4} status={errorLevel} variant="solid">
                    <FormattedError message={errorMsg} keywords={errorKeywords} />
                  </Alert>
                )}
              </Then>
              <Else>
                <Alert rounded="lg" my={2} py={4} status={errorLevel} variant="solid">
                  <FormattedError message={errorMsg} keywords={errorKeywords} />
                </Alert>
              </Else>
            </If>
          </Flex>
        </Box>

        <Flex direction="row" flexWrap="wrap">
          <HStack
            px={3}
            mt={2}
            spacing={1}
            flex="1 0 auto"
            justifyContent={{ base: 'flex-start', lg: 'flex-end' }}
          >
            <If condition={cache.showText && !snapshot && !isError && isCached}>
              <Then>
                <If condition={isMobile}>
                  <Then>
                    <Countdown timeout={cache.timeout} text={web.text.cachePrefix} />
                    <Tooltip hasArrow label={cacheLabel} placement="top">
                      <Box>
                        <DynamicIcon icon={{ bs: 'BsLightningFill' }} color={color} />
                      </Box>
                    </Tooltip>
                  </Then>
                  <Else>
                    <Tooltip hasArrow label={cacheLabel} placement="top">
                      <Box>
                        <DynamicIcon icon={{ bs: 'BsLightningFill' }} color={color} />
                      </Box>
                    </Tooltip>
                    <Countdown timeout={cache.timeout} text={web.text.cachePrefix} />
                  </Else>
                </If>
              </Then>
            </If>
          </HStack>
        </Flex>
      </AccordionPanel>
    </AnimatedAccordionItem>
  );
};

export const Result = memo(forwardRef<HTMLDivElement, ResultProps>(_Result), isEqual);

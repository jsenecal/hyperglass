import { Accordion, Box, Flex, Text } from '@chakra-ui/react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { Result } from '~/components/results/individual';
import { useConfig } from '~/context';
import { AnimatedDiv } from '~/elements';
import { useShareGet, useStrf } from '~/hooks';

import type { NextPage } from 'next';

const ResultPage: NextPage = () => {
  const router = useRouter();
  const { web, messages } = useConfig();
  const strF = useStrf();

  const id = typeof router.query.id === 'string' ? router.query.id : undefined;
  const { data: snapshot, isLoading, error } = useShareGet(id);

  if (!router.isReady || isLoading) {
    return null;
  }

  if (error || !snapshot) {
    return (
      <Flex
        my={4}
        w="100%"
        mx="auto"
        maxW={{ base: '100%', md: '75%' }}
        justifyContent="center"
        alignItems="center"
      >
        <Text>{web.text.shareNotFound}</Text>
      </Flex>
    );
  }

  const banner = strF(web.text.shareSnapshotBanner, {
    timestamp: snapshot.timestamp,
  });

  const expiresDisplay = new Date(snapshot.expiresAt).toLocaleString();
  const expires = strF(web.text.shareExpiresAt, { expires: expiresDisplay });

  const queryTarget =
    typeof snapshot.query.query_target === 'string'
      ? snapshot.query.query_target
      : snapshot.query.query_target[0];

  const freshUrl = `/?location=${encodeURIComponent(
    snapshot.query.query_location,
  )}&target=${encodeURIComponent(queryTarget)}&type=${encodeURIComponent(
    snapshot.query.query_type,
  )}`;

  return (
    <Box w="100%" maxW={{ base: '100%', md: '75%' }} mx="auto">
      <Flex
        mb={3}
        gap={2}
        wrap="wrap"
        fontSize="sm"
        color="gray.500"
        alignItems="center"
        justifyContent="space-between"
        role="region"
        aria-label={banner}
      >
        <Text>{banner}</Text>
        <Text>{expires}</Text>
      </Flex>
      <AnimatedDiv
        p={0}
        my={4}
        w="100%"
        mx="auto"
        rounded="lg"
        textAlign="left"
        borderWidth="1px"
        overflow="hidden"
        initial={{ opacity: 1 }}
        exit={{ opacity: 0, y: 300 }}
        transition={{ duration: 0.3 }}
        animate={{ opacity: 1, y: 0 }}
      >
        {/* Result is an AccordionItem — it must live inside an Accordion */}
        <Accordion defaultIndex={[0]} allowMultiple>
          <Result
            index={0}
            queryLocation={snapshot.query.query_location}
            snapshot={snapshot}
            readOnly
          />
        </Accordion>
      </AnimatedDiv>
      <Flex justifyContent="center" mt={4}>
        <Link href={freshUrl}>{web.text.shareRunFreshQuery}</Link>
      </Flex>
    </Box>
  );
};

export default ResultPage;

import { Box, Flex, Text } from '@chakra-ui/react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { SnapshotResults } from '~/components/results/snapshot-results';
import { useConfig } from '~/context';
import { useShareGet, useStrf } from '~/hooks';

import type { NextPage } from 'next';

const ResultPage: NextPage = () => {
  const router = useRouter();
  const { web } = useConfig();
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
      <SnapshotResults items={[{ queryLocation: snapshot.query.query_location, snapshot }]} />
      <Flex justifyContent="center" mt={4}>
        <Link href={freshUrl}>{web.text.shareRunFreshQuery}</Link>
      </Flex>
    </Box>
  );
};

export default ResultPage;

// `next export` requires getStaticPaths + getStaticProps for dynamic routes.
// We return no pre-rendered paths because share IDs are generated at runtime;
// the Litestar backend serves the SPA shell (index.html) as a fallback for
// /result/<id> and the Next.js client router hydrates the correct page on load.
export function getStaticPaths() {
  return { paths: [], fallback: false };
}

// Required by Next.js alongside getStaticPaths. Returns empty props because
// the page fetches its own data client-side via useShareGet.
export function getStaticProps() {
  return { props: {} };
}

import { Box, Flex, Text } from '@chakra-ui/react';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';
import { SnapshotActions } from '~/components/results/snapshot-actions';
import { SnapshotResults } from '~/components/results/snapshot-results';
import { useConfig } from '~/context';
import { FloatingBackButton } from '~/elements';
import { useShareGet, useStrf } from '~/hooks';

import type { NextPage } from 'next';

const ResultPage: NextPage = () => {
  const { web } = useConfig();
  const strF = useStrf();
  const router = useRouter();

  // This page ships as a single static placeholder export (result/shared.html)
  // that the backend serves for every /result/<id> URL. Because it's a
  // statically-exported SSG route, Next bakes the placeholder param into
  // router.query.id ("shared") and does NOT re-derive it from the address bar,
  // so we parse the real share ID from window.location on the client instead.
  // `id` is undefined until mount, which keeps useShareGet disabled (no fetch
  // during prerender / first paint).
  const [id, setId] = useState<string | undefined>(undefined);
  useEffect(() => {
    const match = window.location.pathname.match(/\/result\/([^/]+)\/?$/);
    setId(match ? decodeURIComponent(match[1]) : undefined);
  }, []);

  const { data: snapshot, isLoading, error } = useShareGet(id);

  if (!id || isLoading) {
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

  const rawTarget = snapshot.query.query_target;
  const queryTarget = typeof rawTarget === 'string' ? rawTarget : rawTarget[0];
  const actionsQuery = {
    queryLocation: snapshot.query.query_location,
    queryType: snapshot.query.query_type,
    queryTarget,
  };

  return (
    <Box w="100%" maxW={{ base: '100%', md: '75%' }} mx="auto">
      <FloatingBackButton isVisible onClick={() => router.push('/')} label={web.text.historyBack} />
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
        <SnapshotActions query={actionsQuery} />
      </Flex>
    </Box>
  );
};

export default ResultPage;

// `next export` requires getStaticPaths + getStaticProps for dynamic routes.
// Share IDs are minted at runtime, so we can't enumerate real paths. We emit a
// single placeholder export (`result/shared.html`) whose __NEXT_DATA__ pins the
// page to `/result/[id]`; the Litestar backend serves this file for every
// /result/<id> request, and the Next.js client router parses the real share ID
// from window.location once `router.isReady`. Returning no paths (the previous
// behavior) emitted no result HTML at all, so the backend fell back to
// index.html — which boots the home page, not this one.
export function getStaticPaths() {
  return { paths: [{ params: { id: 'shared' } }], fallback: false };
}

// Required by Next.js alongside getStaticPaths. Returns empty props because
// the page fetches its own data client-side via useShareGet.
export function getStaticProps() {
  return { props: {} };
}

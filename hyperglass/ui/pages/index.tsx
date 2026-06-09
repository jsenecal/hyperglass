import { Box } from '@chakra-ui/react';
import { AnimatePresence } from 'framer-motion';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/router';
import { useEffect } from 'react';
import { Else, If, Then } from 'react-if';
import { SnapshotResults } from '~/components/results/snapshot-results';
import { useConfig } from '~/context';
import { FloatingBackButton, Loading } from '~/elements';
import { useQueryHistory, useView } from '~/hooks';

import type { NextPage } from 'next';
import type { SnapshotResultsItem } from '~/components/results/snapshot-results';

const LookingGlassForm = dynamic<Dict>(
  () => import('~/components/looking-glass-form').then(i => i.LookingGlassForm),
  {
    loading: Loading,
  },
);

const Results = dynamic<Dict>(() => import('~/components/results').then(i => i.Results), {
  loading: Loading,
});

const RecentQueries = dynamic<Dict>(
  () => import('~/components/history').then(i => i.RecentQueries),
  { ssr: false },
);

const Index: NextPage = () => {
  const view = useView();
  const { web } = useConfig();
  const openId = useQueryHistory(s => s.openId);
  const close = useQueryHistory(s => s.close);
  const entries = useQueryHistory(s => s.entries);
  const router = useRouter();

  const openEntry = openId ? entries.find(e => e.id === openId) : undefined;

  useEffect(() => {
    if (!openEntry) return;
    if (openEntry.shareId) {
      router.push(`/result/${openEntry.shareId}`);
      return;
    }
    const params = new URLSearchParams();
    params.set('location', openEntry.query.queryLocation[0]);
    params.set('type', openEntry.query.queryType);
    if (openEntry.query.queryTarget[0]) params.set('target', openEntry.query.queryTarget[0]);
    router.push(`/?${params.toString()}`, undefined, { shallow: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openEntry?.id]);

  const handleClose = () => {
    close();
    router.push('/', undefined, { shallow: true });
  };

  if (openEntry) {
    const items: SnapshotResultsItem[] = Object.entries(openEntry.results).map(
      ([queryLocation, snapshot]) => ({ queryLocation, snapshot }),
    );
    return (
      <Box w="100%" maxW={{ base: '100%', md: '75%' }} mx="auto">
        <FloatingBackButton isVisible onClick={handleClose} label={web.text.historyBack} />
        <SnapshotResults items={items} showShare />
      </Box>
    );
  }

  return (
    <If condition={view === 'results'}>
      <Then>
        <Results />
      </Then>
      <Else>
        <AnimatePresence>
          <LookingGlassForm />
        </AnimatePresence>
        <RecentQueries />
      </Else>
    </If>
  );
};

export default Index;

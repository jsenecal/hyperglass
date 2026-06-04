import { useCallback } from 'react';
import { useConfig } from '~/context';
import { useQueryHistory } from './use-query-history';

interface RecordHistoryArgs {
  submissionId: string;
  deviceId: string;
  deviceLabel: string;
  directiveHistory: boolean;
  query: { queryType: string; queryTarget: string[] };
  labels: { type: string; target: string };
  snapshot: ResultSnapshot;
}

/**
 * Returns a callback that records a successful result into query history,
 * unless history is disabled globally or for the directive.
 */
export function useRecordHistory(): (args: RecordHistoryArgs) => void {
  const { cache } = useConfig();
  const record = useQueryHistory(s => s.record);

  return useCallback(
    (args: RecordHistoryArgs): void => {
      if (!cache.historyEnabled || !args.directiveHistory) return;
      const { directiveHistory, ...rest } = args;
      record({ ...rest, limit: cache.historyLimit });
    },
    [cache.historyEnabled, cache.historyLimit, record],
  );
}

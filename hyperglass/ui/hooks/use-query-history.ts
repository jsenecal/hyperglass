import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { historyStorage } from '~/util/history-storage';
import { withDev } from '~/util';

export interface HistoryEntry {
  id: string;
  savedAt: number;
  query: { queryLocation: string[]; queryType: string; queryTarget: string[] };
  labels: { locations: string[]; type: string; target: string };
  results: Record<string, ResultSnapshot>;
}

export interface RecordInput {
  submissionId: string;
  deviceId: string;
  deviceLabel: string;
  query: { queryType: string; queryTarget: string[] };
  labels: { type: string; target: string };
  snapshot: ResultSnapshot;
  limit: number;
}

interface QueryHistoryState {
  entries: HistoryEntry[];
  openId: string | null;
  record(input: RecordInput): void;
  remove(id: string): void;
  clear(): void;
  open(id: string): void;
  close(): void;
}

const uniq = (values: string[]): string[] => Array.from(new Set(values));

export const useQueryHistory = create<QueryHistoryState>()(
  persist(
    withDev<QueryHistoryState>(
      (set, get) => ({
        entries: [],
        openId: null,

        record(input: RecordInput): void {
          const { submissionId, deviceId, deviceLabel, query, labels, snapshot, limit } = input;
          const existing = get().entries.find(e => e.id === submissionId);

          const entry: HistoryEntry = existing
            ? {
                ...existing,
                results: { ...existing.results, [deviceId]: snapshot },
                query: {
                  ...existing.query,
                  queryLocation: uniq([...existing.query.queryLocation, deviceId]),
                },
                labels: {
                  ...existing.labels,
                  locations: uniq([...existing.labels.locations, deviceLabel]),
                },
              }
            : {
                id: submissionId,
                savedAt: Date.now(),
                query: {
                  queryLocation: [deviceId],
                  queryType: query.queryType,
                  queryTarget: query.queryTarget,
                },
                labels: { locations: [deviceLabel], type: labels.type, target: labels.target },
                results: { [deviceId]: snapshot },
              };

          const others = get().entries.filter(e => e.id !== submissionId);
          set({ entries: [entry, ...others].slice(0, Math.max(0, limit)) });
        },

        remove(id: string): void {
          set(state => ({ entries: state.entries.filter(e => e.id !== id) }));
        },

        clear(): void {
          set({ entries: [] });
        },

        open(id: string): void {
          set({ openId: id });
        },

        close(): void {
          set({ openId: null });
        },
      }),
      'useQueryHistory',
    ),
    {
      name: 'hyperglass.queryHistory',
      version: 1,
      storage: createJSONStorage(() => historyStorage),
      partialize: (state): Pick<QueryHistoryState, 'entries'> => ({ entries: state.entries }),
    },
  ),
);

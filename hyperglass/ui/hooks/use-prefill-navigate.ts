import { useRouter } from 'next/router';
import { useCallback } from 'react';

export interface PrefillQuery {
  queryLocation: string;
  queryType: string;
  /** Single target value; omitted/empty means "new target". */
  queryTarget?: string;
}

/**
 * Navigate to the looking-glass home with the form pre-filled from a snapshot's
 * query. When `run` is true, append `run=1` so the form auto-submits a fresh
 * live query on arrival (consumed by LookingGlassForm's URL prefill effect).
 */
export function usePrefillNavigate(): (q: PrefillQuery, opts?: { run?: boolean }) => void {
  const router = useRouter();
  return useCallback(
    (q: PrefillQuery, opts?: { run?: boolean }) => {
      const params = new URLSearchParams();
      params.set('location', q.queryLocation);
      params.set('type', q.queryType);
      if (q.queryTarget) params.set('target', q.queryTarget);
      if (opts?.run && q.queryTarget) params.set('run', '1');
      router.push(`/?${params.toString()}`);
    },
    [router],
  );
}

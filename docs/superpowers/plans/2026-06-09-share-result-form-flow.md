# Share / result / form-prefill flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken result-share / form-prefill flow — prefilled forms actually populate and submit, back controls are consistent, shared results offer re-run, and opened results are reflected in the URL.

**Architecture:** Collapse the three drifting form-state representations (react-hook-form values, Zustand `form`, Zustand `selections`) behind a single `prefillForm` entry point plus a Zustand→RHF mirror effect. Generalize the green floating back control. Add deep-link navigation (with optional auto-run) for re-running shared snapshots. Reflect opened results in the address bar.

**Tech Stack:** Next.js 13 (pages router, static export), React, Zustand, react-hook-form + vest, Chakra UI, Vitest + jsdom, Playwright (headless e2e gate).

**Working directory:** `hyperglass/ui/`. All paths below are relative to it unless noted. Run UI commands with `task pnpm <args>` from repo root, or `pnpm <args>` inside `hyperglass/ui/`. Lint: `npx biome lint .`; typecheck: `npx tsc --noEmit`; tests: `npx vitest --run <path>`.

**Scope:** UI only. No backend changes. All user-visible strings already exist as config keys in `hyperglass/models/config/web.py` (`historyRerun`, `historyNewTarget`, `historyBack`, `shareRunFreshQuery`); do not hard-code strings.

**Confirmed during planning (do not re-investigate):**
- `LocationCard` already syncs `isChecked` from `defaultChecked` via a `useEffect` — no change needed; cards reflect prefill once `form.queryLocation` updates.
- `useQueryHistory` already excludes `openId` from `persist` (partialize keeps only `entries`) — no change needed for that.
- `ResultSnapshot` has no `query`; only `ShareResponse` (the `/result/<id>` payload) does. Shared re-run actions live on the result page where `ShareResponse` is available.

---

## File structure

- `hooks/use-form-state.ts` — `prefillForm` becomes full source of truth (adds `selections.queryType`).
- `components/looking-glass-form.tsx` — Zustand→RHF mirror; URL effect delegates to `prefillForm`; consumes `?run=1` auto-run.
- `elements/floating-back-button.tsx` (new) — presentational floating green back control `{ isVisible, onClick, label }`.
- `elements/index.ts` — export the new element.
- `components/reset-button.tsx` — re-implemented on top of `FloatingBackButton` (live-results reset).
- `pages/index.tsx` — opened-history view uses the floating back control instead of the text button.
- `hooks/use-prefill-navigate.ts` (new) — builds the deep-link and navigates home (optionally with `run`).
- `components/results/snapshot-actions.tsx` (new) — Re-run / New-target icon buttons for snapshots.
- `pages/result/[id].tsx` — floating back arrow → `/`; replace the fresh-query link with `SnapshotActions`.
- `hooks/use-query-history.ts` — `shareId` field + `setShareId` action + URL side effects in `open`/`close`.
- `components/results/share-button.tsx` — optional `onShared(shareId)` callback.
- `components/history/history-entry-row.tsx` — wire `onShared` → `setShareId`.

---

## Phase 1 — prefill correctness

### Task 1: `prefillForm` populates `selections.queryType`

**Files:**
- Modify: `hooks/use-form-state.ts` (the `prefillForm` method, ~lines 204-239)
- Test: `hooks/use-form-state.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `hooks/use-form-state.test.tsx` (follow the existing `getDevice` mock pattern already in that file; if a device/directive fixture helper exists, reuse it). The fixture device must expose a directive with `id: 'juniper_bgp_route'`, `name: 'BGP Route'`, `groups: []`.

```tsx
it('prefillForm sets selections.queryType from the matching directive', () => {
  const getDevice = makeGetDevice(); // existing helper returning a device w/ the directive
  useFormState.getState().prefillForm(
    { queryLocation: ['test1'], queryType: 'juniper_bgp_route', queryTarget: ['192.0.2.0/24'] },
    getDevice,
  );
  const { selections, form } = useFormState.getState();
  expect(form.queryType).toBe('juniper_bgp_route');
  expect(selections.queryType).toEqual({ value: 'juniper_bgp_route', label: 'BGP Route' });
});

it('prefillForm leaves selections.queryType null for an empty type (new target)', () => {
  const getDevice = makeGetDevice();
  useFormState.getState().prefillForm(
    { queryLocation: ['test1'], queryType: '', queryTarget: [] },
    getDevice,
  );
  expect(useFormState.getState().selections.queryType).toBeNull();
});
```

If `makeGetDevice` does not already exist in the test file, define a local helper that returns a device matching `~/types` `Device` with one directive as above, and `null` for unknown ids.

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest --run hooks/use-form-state.test.tsx -t "selections.queryType"`
Expected: FAIL — `selections.queryType` is `null` for the first test (current code hardcodes `null`).

- [ ] **Step 3: Implement**

In `hooks/use-form-state.ts`, replace the `set({...})` block inside `prefillForm` so `selections.queryType` is derived from the computed `directives`:

```ts
    const directives = dedupObjectArray(intersectingDirectives, 'id');

    const matchingType = directives.find(d => d.id === query.queryType) ?? null;
    const queryTypeSelection = matchingType
      ? { value: matchingType.id, label: matchingType.name }
      : null;

    set({
      form: {
        queryLocation: validLocations,
        queryType: query.queryType,
        queryTarget: query.queryTarget,
      },
      selections: {
        queryLocation: validDevices.map(d => ({ value: d.id, label: d.name })),
        queryType: queryTypeSelection,
      },
      filtered: { groups: intersecting, types: directives },
      target: { display: query.queryTarget.join(' ') },
    });

    return validLocations;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest --run hooks/use-form-state.test.tsx`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add hooks/use-form-state.ts hooks/use-form-state.test.tsx
git commit -m "fix(ui): prefillForm populates the query-type selection"
```

---

### Task 2: Zustand→RHF mirror + URL prefill via `prefillForm` + auto-run

**Files:**
- Modify: `components/looking-glass-form.tsx`
- Test: `components/looking-glass-form.test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `components/looking-glass-form.test.tsx` (it already has a `?location=` prefill test and `next/router` mock; follow that mock style — set `router.query` and `isReady: true`).

```tsx
it('prefills type + target from URL and mirrors them into react-hook-form', async () => {
  // Arrange router.query = { location: 'test1', type: 'juniper_bgp_route', target: '192.0.2.0/24' }
  // (use the file's existing router-mock helper)
  renderForm();
  // selections.queryType drives the visible type value:
  await waitFor(() =>
    expect(useFormState.getState().selections.queryType).toEqual({
      value: 'juniper_bgp_route',
      label: 'BGP Route',
    }),
  );
  // RHF mirror: the submit button is gated on a valid form; target present => SubmitButton visible.
  await waitFor(() => expect(screen.getByLabelText(/submit/i)).toBeInTheDocument());
});

it('auto-runs when ?run=1 is present', async () => {
  // router.query = { location: 'test1', type: 'juniper_bgp_route', target: '192.0.2.0/24', run: '1' }
  renderForm();
  await waitFor(() => expect(useFormState.getState().status).toBe('results'));
  expect(useFormState.getState().submissionId).not.toBeNull();
});
```

Match the file's existing render/mocks (`renderForm`, `screen`, `waitFor`). The submit-button accessible name comes from `web.text` in the test config; adjust the matcher to the file's existing convention if it differs.

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest --run components/looking-glass-form.test.tsx -t "mirrors them into react-hook-form"`
Expected: FAIL — `selections.queryType` stays `null` (URL path never set it) and/or auto-run test fails (no `run` handling).

- [ ] **Step 3: Implement**

In `components/looking-glass-form.tsx`:

(a) Replace the URL-param prefill `useEffect` (currently ~lines 141-172) with one that delegates to `prefillForm` and handles `run`:

```tsx
  const prefillForm = useFormState(s => s.prefillForm);

  // Pre-fill from URL query params (?location=&target=&type=[&run=1]). Applied
  // once on mount when router.isReady; the ref guard prevents re-applying after
  // the user edits the form. Delegates to prefillForm (single source of truth);
  // the Zustand→RHF mirror below keeps react-hook-form in sync for validation.
  const prefillApplied = useRef(false);
  useEffect(() => {
    if (!router.isReady || prefillApplied.current) return;
    const { location, target, type, run } = router.query;
    if (typeof location !== 'string') {
      prefillApplied.current = true;
      return;
    }
    prefillApplied.current = true;

    const valid = prefillForm(
      {
        queryLocation: [location],
        queryType: typeof type === 'string' ? type : '',
        queryTarget: typeof target === 'string' ? [target] : [],
      },
      getDevice,
    );

    const canRun =
      run === '1' &&
      valid.length > 0 &&
      typeof type === 'string' &&
      type.length > 0 &&
      typeof target === 'string' &&
      target.length > 0;
    if (canRun) {
      setSubmissionId(makeSubmissionId());
      setStatus('results');
    }
  }, [router.isReady, router.query]); // eslint-disable-line react-hooks/exhaustive-deps
```

(b) Add the Zustand→RHF mirror effect (anywhere after `formInstance` is created):

```tsx
  // Mirror Zustand form values into react-hook-form. Prefill paths write to
  // Zustand (form/selections) but not RHF; without this, RHF's validation still
  // sees empty values and a prefilled form cannot be submitted.
  useEffect(() => {
    setValue('queryLocation', form.queryLocation);
    setValue('queryType', form.queryType);
    setValue('queryTarget', form.queryTarget);
  }, [form.queryLocation, form.queryType, form.queryTarget, setValue]);
```

`setSubmissionId`, `setStatus`, `getDevice`, `makeSubmissionId`, and `form` are already in scope in this component. Remove now-unused `setSelection`/`setTarget`/`setFormValue`/`locationChange` references **only if** they become unused after the rewrite (they are still used by `handleChange`; keep those).

- [ ] **Step 4: Run tests + lint + typecheck**

Run:
```
npx vitest --run components/looking-glass-form.test.tsx
npx biome lint components/looking-glass-form.tsx
npx tsc --noEmit
```
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add components/looking-glass-form.tsx components/looking-glass-form.test.tsx
git commit -m "fix(ui): sync prefilled form into react-hook-form and support URL auto-run"
```

---

### Task 3: History Re-run / New-target populate correctly (regression test)

**Files:**
- Test: `components/history/history-entry-row.test.tsx`

This behavior is fixed by Tasks 1–2; add explicit assertions so it can't regress.

- [ ] **Step 1: Write the test**

Extend the existing Re-run / New-target tests (the file already renders a row and triggers these). Assert the type selection is populated:

```tsx
it('Re-run prefills location, type selection, and target', () => {
  // render row for an entry with query { queryLocation:['test1'], queryType:'juniper_bgp_route', queryTarget:['192.0.2.0/24'] }
  fireEvent.click(screen.getByLabelText(web.text.historyRerun));
  const st = useFormState.getState();
  expect(st.form.queryType).toBe('juniper_bgp_route');
  expect(st.selections.queryType).toEqual({ value: 'juniper_bgp_route', label: 'BGP Route' });
  expect(st.form.queryTarget).toEqual(['192.0.2.0/24']);
});

it('New target prefills type selection but clears target', () => {
  fireEvent.click(screen.getByLabelText(web.text.historyNewTarget));
  const st = useFormState.getState();
  expect(st.selections.queryType).toEqual({ value: 'juniper_bgp_route', label: 'BGP Route' });
  expect(st.form.queryTarget).toEqual([]);
});
```

Reuse the file's existing config/`web.text` access and entry fixtures. (Note: New-target passes `queryType` through, so the type selection is preserved — only target is cleared.)

- [ ] **Step 2: Run**

Run: `npx vitest --run components/history/history-entry-row.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add components/history/history-entry-row.test.tsx
git commit -m "test(ui): assert history re-run/new-target populate the type selection"
```

---

## Phase 2 — consistent back control + shared re-run

### Task 4: `FloatingBackButton` element + reuse in `ResetButton`

**Files:**
- Create: `elements/floating-back-button.tsx`
- Modify: `elements/index.ts`, `components/reset-button.tsx`
- Test: `elements/floating-back-button.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { ChakraProvider } from '@chakra-ui/react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FloatingBackButton } from './floating-back-button';

const renderEl = (props: Partial<React.ComponentProps<typeof FloatingBackButton>>) =>
  render(
    <ChakraProvider>
      <FloatingBackButton isVisible onClick={() => {}} label="Back" {...props} />
    </ChakraProvider>,
  );

describe('FloatingBackButton', () => {
  it('renders when visible and fires onClick', () => {
    const onClick = vi.fn();
    renderEl({ onClick });
    fireEvent.click(screen.getByLabelText('Back'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not render the button when not visible', () => {
    renderEl({ isVisible: false });
    expect(screen.queryByLabelText('Back')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest --run elements/floating-back-button.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the element**

Create `elements/floating-back-button.tsx` (extracted from the existing `ResetButton` styling):

```tsx
import { Flex, IconButton } from '@chakra-ui/react';
import { AnimatePresence } from 'framer-motion';
import { AnimatedDiv, DynamicIcon } from '~/elements';
import { useColorValue, useOpposingColor } from '~/hooks';

import type { FlexProps } from '@chakra-ui/react';

interface FloatingBackButtonProps extends FlexProps {
  isVisible: boolean;
  onClick(): void;
  label: string;
  /** Extra bottom offset (e.g. developer-mode bar). */
  raised?: boolean;
}

export const FloatingBackButton = (props: FloatingBackButtonProps): JSX.Element => {
  const { isVisible, onClick, label, raised = false, ...rest } = props;
  const bg = useColorValue('primary.500', 'primary.300');
  const color = useOpposingColor(bg);
  return (
    <AnimatePresence>
      {isVisible && (
        <AnimatedDiv
          bg={bg}
          left={0}
          zIndex={4}
          bottom={24}
          boxSize={12}
          color={color}
          position="fixed"
          animate={{ x: 0 }}
          exit={{ x: '-100%' }}
          borderRightRadius="md"
          initial={{ x: '-100%' }}
          mb={raised ? { base: 0, lg: 14 } : undefined}
          transition={{ duration: 0.15, ease: [0.4, 0, 0.2, 1] }}
        >
          <Flex boxSize="100%" justifyContent="center" alignItems="center" {...rest}>
            <IconButton
              lineHeight={0}
              color="current"
              variant="unstyled"
              aria-label={label}
              onClick={onClick}
              icon={<DynamicIcon icon={{ fa: 'FaAngleLeft' }} boxSize={8} />}
            />
          </Flex>
        </AnimatedDiv>
      )}
    </AnimatePresence>
  );
};
```

Add to `elements/index.ts`:

```ts
export * from './floating-back-button';
```

- [ ] **Step 4: Re-implement `ResetButton` on top of it**

Replace `components/reset-button.tsx` body with:

```tsx
import { useConfig } from '~/context';
import { FloatingBackButton } from '~/elements';
import { useFormState } from '~/hooks';

interface ResetButtonProps {
  developerMode: boolean;
  resetForm(): void;
}

export const ResetButton = (props: ResetButtonProps): JSX.Element => {
  const { developerMode, resetForm } = props;
  const status = useFormState(s => s.status);
  const { web } = useConfig();
  return (
    <FloatingBackButton
      isVisible={status === 'results'}
      onClick={resetForm}
      label={web.text.historyBack}
      raised={developerMode}
    />
  );
};
```

If `ResetButton`'s call site passed `FlexProps` spread (`...rest`), check `components/layout.tsx` for how it's rendered and drop any now-unsupported props. Run typecheck to catch this.

- [ ] **Step 5: Run tests + typecheck + lint**

Run:
```
npx vitest --run elements/floating-back-button.test.tsx
npx tsc --noEmit
npx biome lint elements/floating-back-button.tsx components/reset-button.tsx
```
Expected: PASS / clean.

- [ ] **Step 6: Commit**

```bash
git add elements/floating-back-button.tsx elements/floating-back-button.test.tsx elements/index.ts components/reset-button.tsx
git commit -m "refactor(ui): extract FloatingBackButton and build ResetButton on it"
```

---

### Task 5: Opened-history view uses the floating back control

**Files:**
- Modify: `pages/index.tsx`

- [ ] **Step 1: Implement**

In `pages/index.tsx`, replace the opened-entry `<Flex>…<Button>{web.text.historyBack}</Button></Flex>` block with the floating control, and drop the now-unused `Button`/`Flex` import if unused:

```tsx
  if (openEntry) {
    const items: SnapshotResultsItem[] = Object.entries(openEntry.results).map(
      ([queryLocation, snapshot]) => ({ queryLocation, snapshot }),
    );
    return (
      <Box w="100%" maxW={{ base: '100%', md: '75%' }} mx="auto">
        <FloatingBackButton isVisible onClick={close} label={web.text.historyBack} />
        <SnapshotResults items={items} showShare />
      </Box>
    );
  }
```

Add `import { FloatingBackButton } from '~/elements';` and remove `Button`/`Flex` from the chakra import if they are no longer referenced elsewhere in the file (`Box` is still used).

- [ ] **Step 2: Typecheck + lint**

Run: `npx tsc --noEmit && npx biome lint pages/index.tsx`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add pages/index.tsx
git commit -m "fix(ui): use the floating back control in the opened-history view"
```

---

### Task 6: `usePrefillNavigate` hook + `SnapshotActions` component

**Files:**
- Create: `hooks/use-prefill-navigate.ts`, `components/results/snapshot-actions.tsx`
- Modify: `hooks/index.ts` (if hooks are re-exported there — check; otherwise import directly)
- Test: `components/results/snapshot-actions.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { ChakraProvider } from '@chakra-ui/react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const push = vi.fn();
vi.mock('next/router', () => ({ useRouter: () => ({ push }) }));
vi.mock('~/context', () => ({
  useConfig: () => ({ web: { text: { historyRerun: 'Run again', historyNewTarget: 'Run with a new target' } } }),
}));

import { SnapshotActions } from './snapshot-actions';

const q = { queryLocation: 'test1', queryType: 'juniper_bgp_route', queryTarget: '192.0.2.0/24' };

describe('SnapshotActions', () => {
  it('Re-run navigates home with prefill + run flag', () => {
    render(
      <ChakraProvider>
        <SnapshotActions query={q} />
      </ChakraProvider>,
    );
    fireEvent.click(screen.getByLabelText('Run again'));
    expect(push).toHaveBeenCalledWith(
      '/?location=test1&type=juniper_bgp_route&target=192.0.2.0%2F24&run=1',
    );
  });

  it('New target navigates home with prefill, no run flag and no target', () => {
    render(
      <ChakraProvider>
        <SnapshotActions query={q} />
      </ChakraProvider>,
    );
    fireEvent.click(screen.getByLabelText('Run with a new target'));
    expect(push).toHaveBeenCalledWith('/?location=test1&type=juniper_bgp_route');
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest --run components/results/snapshot-actions.test.tsx`
Expected: FAIL — modules do not exist.

- [ ] **Step 3: Implement the hook**

Create `hooks/use-prefill-navigate.ts`:

```ts
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
```

If `hooks/index.ts` re-exports hooks, add `export * from './use-prefill-navigate';` there.

- [ ] **Step 4: Implement the component**

Create `components/results/snapshot-actions.tsx`:

```tsx
import { Button, HStack, Tooltip } from '@chakra-ui/react';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';
import { usePrefillNavigate } from '~/hooks/use-prefill-navigate';

export interface SnapshotActionsProps {
  query: { queryLocation: string; queryType: string; queryTarget: string };
}

const iconBtn = {
  mx: 1,
  size: 'sm' as const,
  variant: 'ghost' as const,
  colorScheme: 'secondary' as const,
};

export const SnapshotActions = (props: SnapshotActionsProps): JSX.Element => {
  const { query } = props;
  const { web } = useConfig();
  const navigate = usePrefillNavigate();

  return (
    <HStack spacing={0} flex="0 0 auto">
      <Tooltip hasArrow label={web.text.historyRerun} placement="top">
        <Button
          {...iconBtn}
          aria-label={web.text.historyRerun}
          onClick={() =>
            navigate(
              { queryLocation: query.queryLocation, queryType: query.queryType, queryTarget: query.queryTarget },
              { run: true },
            )
          }
        >
          <DynamicIcon icon={{ fi: 'FiRepeat' }} boxSize="16px" />
        </Button>
      </Tooltip>
      <Tooltip hasArrow label={web.text.historyNewTarget} placement="top">
        <Button
          {...iconBtn}
          aria-label={web.text.historyNewTarget}
          onClick={() => navigate({ queryLocation: query.queryLocation, queryType: query.queryType })}
        >
          <DynamicIcon icon={{ fi: 'FiEdit' }} boxSize="16px" />
        </Button>
      </Tooltip>
    </HStack>
  );
};
```

- [ ] **Step 5: Run tests + typecheck + lint**

Run:
```
npx vitest --run components/results/snapshot-actions.test.tsx
npx tsc --noEmit
npx biome lint hooks/use-prefill-navigate.ts components/results/snapshot-actions.tsx
```
Expected: PASS / clean.

- [ ] **Step 6: Commit**

```bash
git add hooks/use-prefill-navigate.ts components/results/snapshot-actions.tsx components/results/snapshot-actions.test.tsx hooks/index.ts
git commit -m "feat(ui): add snapshot re-run/new-target actions with prefill navigation"
```

---

### Task 7: Wire the shared result page (back arrow + SnapshotActions)

**Files:**
- Modify: `pages/result/[id].tsx`
- Test: `__tests__/pages/result/[id].test.tsx`

- [ ] **Step 1: Write the failing test**

Add to `__tests__/pages/result/[id].test.tsx` (it already mocks `~/context` and sets `window.location`; reuse `SHARE_ID` and the fake snapshot). The snapshot fake's `query` uses snake_case keys.

```tsx
it('renders re-run action that navigates home with prefill + run flag', async () => {
  (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockResponse({}));
  render(<ResultPage />, { wrapper });
  const rerun = await screen.findByLabelText('Run again'); // web.text.historyRerun from test config
  fireEvent.click(rerun);
  expect(push).toHaveBeenCalledWith(
    expect.stringContaining('/?location=test1&type=juniper_bgp_route&target=192.0.2.0%2F24&run=1'),
  );
});
```

Add `historyRerun`/`historyNewTarget` to the test's `~/context` `web.text` mock, add a `next/router` mock exposing a `push` spy (the page currently doesn't import the router — add the mock at top of file), and import `fireEvent`.

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest --run "__tests__/pages/result/[id].test.tsx" -t "re-run action"`
Expected: FAIL — no such control yet.

- [ ] **Step 3: Implement**

In `pages/result/[id].tsx`:

- Add `import { FloatingBackButton } from '~/elements';`, `import { useRouter } from 'next/router';`, and `import { SnapshotActions } from '~/components/results/snapshot-actions';`.
- Normalize the snapshot query (target may be string or string[]):

```tsx
  const router = useRouter();
  const rawTarget = snapshot.query.query_target;
  const queryTarget = typeof rawTarget === 'string' ? rawTarget : rawTarget[0];
  const actionsQuery = {
    queryLocation: snapshot.query.query_location,
    queryType: snapshot.query.query_type,
    queryTarget,
  };
```

- Replace the existing `freshUrl`/`<Link>` block with `<SnapshotActions query={actionsQuery} />`, and add the floating back arrow at the top of the returned `<Box>`:

```tsx
  return (
    <Box w="100%" maxW={{ base: '100%', md: '75%' }} mx="auto">
      <FloatingBackButton isVisible onClick={() => router.push('/')} label={web.text.historyBack} />
      <Flex /* existing banner row: keep "Snapshot taken at…" + "Expires…" */ >
        <Text>{banner}</Text>
        <Text>{expires}</Text>
      </Flex>
      <SnapshotResults items={[{ queryLocation: snapshot.query.query_location, snapshot }]} />
      <Flex justifyContent="center" mt={4}>
        <SnapshotActions query={actionsQuery} />
      </Flex>
    </Box>
  );
```

Remove the now-unused `Link` import and the `freshUrl`/`strF(web.text.shareRunFreshQuery…)` usage if no longer referenced.

- [ ] **Step 4: Run tests + typecheck + lint**

Run:
```
npx vitest --run "__tests__/pages/result/[id].test.tsx"
npx tsc --noEmit
npx biome lint "pages/result/[id].tsx"
```
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add "pages/result/[id].tsx" "__tests__/pages/result/[id].test.tsx"
git commit -m "feat(ui): shared result page gets a back arrow and re-run actions"
```

---

### Task 8: End-to-end browser gate for Phases 1–2

**Files:**
- Create (temporary, deleted at end): `verify-flow.mjs`

This is the real-browser gate. It mirrors the harness used for the share-download fix.

- [ ] **Step 1: Build the export**

```bash
cp ../../.tests/hyperglass.json ./hyperglass.json
export NODE_OPTIONS=--openssl-legacy-provider
NODE_ENV=production npx next build
```
Expected: build succeeds; `out/result/shared.html` and `out/index.html` exist.

- [ ] **Step 2: Write the verification script**

Create `hyperglass/ui/verify-flow.mjs` — a static server that (a) serves `out/`, (b) serves `out/result/shared.html` for `/result/<id>`, (c) fakes `GET /api/query/share/<id>` with a full `ShareResponse` (use the `.tests/hyperglass.json` device id `example_device` for `query_location`), and (d) fakes `POST /api/query` so an auto-run resolves. Drive it with Playwright (resolve the package from the npx cache as before: `import pw from '<npx-cache>/playwright/index.js'`).

Assertions:
1. Load `/result/<id>` → the snapshot output renders and a "Run again" control is present.
2. Click "Run again" → URL becomes `/?location=example_device&type=…&target=…&run=1`, the form is populated, and the app transitions to the results view (auto-run fired — assert a `POST /api/query` was received, or the results view rendered).
3. The floating back arrow (aria-label "Back") is present on `/result/<id>` and navigates to `/`.

- [ ] **Step 3: Run the verification**

```bash
node hyperglass/ui/verify-flow.mjs
```
Expected: prints `PASS` and exits 0. If it fails, return to systematic-debugging — do NOT proceed.

- [ ] **Step 4: Clean up build artifacts**

```bash
rm -f hyperglass/ui/verify-flow.mjs hyperglass/ui/hyperglass.json
rm -rf hyperglass/ui/out
```

- [ ] **Step 5: Commit (only if a real source fix was needed)**

If Steps 1–3 surfaced a bug requiring a source change, commit it with a `fix(ui):` message. Otherwise no commit (artifacts were removed).

---

## Phase 3 — URL reflects opened results

### Task 9: `shareId` on history entries + capture on share

**Files:**
- Modify: `hooks/use-query-history.ts`, `components/results/share-button.tsx`, `components/history/history-entry-row.tsx`
- Test: `hooks/use-query-history.test.tsx`, `components/results/share-button.test.tsx`

- [ ] **Step 1: Write the failing test (store)**

In `hooks/use-query-history.test.tsx`:

```tsx
it('setShareId stores a share id on the matching entry', () => {
  const store = useQueryHistory.getState();
  // seed one entry via record(...) using the file's existing helper/fixture, capture its id
  const id = useQueryHistory.getState().entries[0].id;
  useQueryHistory.getState().setShareId(id, 'ABCDEFGHIJK');
  expect(useQueryHistory.getState().entries[0].shareId).toBe('ABCDEFGHIJK');
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest --run hooks/use-query-history.test.tsx -t "setShareId"`
Expected: FAIL — no `setShareId`.

- [ ] **Step 3: Implement store changes**

In `hooks/use-query-history.ts`:
- Add `shareId?: string;` to the `HistoryEntry` interface.
- Add to the state interface: `setShareId(id: string, shareId: string): void;`
- Implement:

```ts
        setShareId(id: string, shareId: string): void {
          set(state => ({
            entries: state.entries.map(e => (e.id === id ? { ...e, shareId } : e)),
          }));
        },
```

- [ ] **Step 4: Write the failing test (ShareButton callback)**

In `components/results/share-button.test.tsx`, add a test that when the mutation succeeds, `onShared` is called with the minted id. Follow the file's existing `useShareCreate` mock pattern (it mocks the hook / fetch). Assert:

```tsx
it('calls onShared with the minted id on success', async () => {
  const onShared = vi.fn();
  // render <ShareButton cacheId="cache1" onShared={onShared} /> with a mocked success returning { id: 'ABCDEFGHIJK', url, expiresAt }
  // trigger the share click
  await waitFor(() => expect(onShared).toHaveBeenCalledWith('ABCDEFGHIJK'));
});
```

- [ ] **Step 5: Run to verify it fails**

Run: `npx vitest --run components/results/share-button.test.tsx -t "onShared"`
Expected: FAIL — no `onShared` prop.

- [ ] **Step 6: Implement ShareButton callback**

In `components/results/share-button.tsx`:
- Extend props: `export interface ShareButtonProps { cacheId: string; onShared?: (shareId: string) => void; }`
- Fire it once when the mutation succeeds:

```tsx
  useEffect(() => {
    if (isSuccess && data?.id) onShared?.(data.id);
  }, [isSuccess, data?.id]); // eslint-disable-line react-hooks/exhaustive-deps
```

(`onShared` destructured from props.)

- [ ] **Step 7: Wire history-entry-row**

In `components/history/history-entry-row.tsx`, pass the callback:

```tsx
  const setShareId = useQueryHistory(s => s.setShareId);
  // …
  {isSingleDevice && (
    <ShareButton
      cacheId={entry.results[deviceIds[0]].id}
      onShared={shareId => setShareId(entry.id, shareId)}
    />
  )}
```

- [ ] **Step 8: Run all affected tests + typecheck + lint**

Run:
```
npx vitest --run hooks/use-query-history.test.tsx components/results/share-button.test.tsx components/history/history-entry-row.test.tsx
npx tsc --noEmit
npx biome lint hooks/use-query-history.ts components/results/share-button.tsx components/history/history-entry-row.tsx
```
Expected: PASS / clean.

- [ ] **Step 9: Commit**

```bash
git add hooks/use-query-history.ts hooks/use-query-history.test.tsx components/results/share-button.tsx components/results/share-button.test.tsx components/history/history-entry-row.tsx
git commit -m "feat(ui): remember a history entry's share id when shared"
```

---

### Task 10: Reflect opened results in the URL

**Files:**
- Modify: `hooks/use-query-history.ts` (open/close) and/or `pages/index.tsx`
- Test: `pages/index.test.tsx` (create if absent) or extend an existing index/history test

The router is not available inside a Zustand store, so perform the URL side effect in `pages/index.tsx` via an effect keyed on `openId`, not inside `open()`/`close()`.

- [ ] **Step 1: Write the failing test**

In a test for `pages/index.tsx` (mock `next/router` with `push` spy and a `query` object; mock `useQueryHistory` and `useConfig`):

```tsx
it('opening an un-shared entry shallow-pushes the deep-link', async () => {
  // useQueryHistory returns openId='e1', entries=[{ id:'e1', query:{queryLocation:['test1'],queryType:'juniper_bgp_route',queryTarget:['192.0.2.0/24']}, results:{...}, labels:{...} }]
  render(<Index />);
  await waitFor(() =>
    expect(push).toHaveBeenCalledWith(
      '/?location=test1&type=juniper_bgp_route&target=192.0.2.0%2F24',
      undefined,
      { shallow: true },
    ),
  );
});

it('opening a shared entry navigates to /result/<shareId>', async () => {
  // same entry but with shareId:'ABCDEFGHIJK'
  render(<Index />);
  await waitFor(() => expect(push).toHaveBeenCalledWith('/result/ABCDEFGHIJK'));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest --run pages/index.test.tsx`
Expected: FAIL — no URL push on open.

- [ ] **Step 3: Implement**

In `pages/index.tsx`, add an effect that runs when `openEntry` changes:

```tsx
  const router = useRouter();
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
```

And in `close`'s handler path, restore `/`: change the `close` button/back control to also shallow-reset the URL. Since `close` lives in the store, do it in the same component — wrap the back control's `onClick`:

```tsx
  const close = useQueryHistory(s => s.close);
  const handleClose = () => {
    close();
    router.push('/', undefined, { shallow: true });
  };
  // …in the openEntry return: onClick={handleClose}
```

`useRouter` and `useEffect` must be imported in `pages/index.tsx`.

- [ ] **Step 4: Run tests + typecheck + lint**

Run:
```
npx vitest --run pages/index.test.tsx
npx tsc --noEmit
npx biome lint pages/index.tsx
```
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add pages/index.tsx pages/index.test.tsx
git commit -m "feat(ui): reflect an opened history result in the address bar"
```

---

### Task 11: Final full verification + changelog

**Files:**
- Modify: `CHANGELOG.md` (repo root)

- [ ] **Step 1: Full UI suite + lint + typecheck**

Run (from repo root):
```
task pnpm test
npx --prefix hyperglass/ui biome lint hyperglass/ui     # or: cd hyperglass/ui && npx biome lint .
cd hyperglass/ui && npx tsc --noEmit
```
Expected: all tests pass; Biome clean; tsc clean.

- [ ] **Step 2: Re-run the end-to-end browser gate (Task 8 script) including the Phase-3 URL behavior**

Rebuild the export and re-run the verification (add an assertion that opening a shared entry lands on `/result/<id>`). Expected: PASS. Clean up artifacts afterward.

- [ ] **Step 3: Changelog**

Add an Unreleased entry to `CHANGELOG.md`:

```markdown
## [Unreleased]

### Fixed

- Re-running a query from history or a shared result now populates the form correctly (location, query type, and target) and the form can be submitted; previously the query type was blank and a prefilled "new target" form could not be submitted.
- The "view result" and shared-result pages now use the same green bottom-left back control as live results, replacing the inconsistent text button. The shared page keeps its snapshot/expiry banner.
- Shared results now offer Re-run and "new target" actions; "Run a fresh query" no longer lands on an empty form.

### Added

- Opening a stored result reflects it in the address bar (a `/result/<id>` link when the result has been shared, otherwise a bookmarkable deep link).
```

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): record share/result/form-prefill fixes"
```

---

## Self-review notes (addressed)

- **Spec coverage:** item 1 → Tasks 1–3; item 2 → Tasks 4,5,7; item 3 → Tasks 9,10; item 4 → Tasks 1–2 (prefill), 6,7 (actions); testing/e2e gate → Tasks 8,11.
- **Dropped from spec (correctly):** LocationCard change (already self-syncs) and `openId` persist exclusion (already partialized) — confirmed during planning; no tasks needed.
- **Type consistency:** `FloatingBackButton` props `{ isVisible, onClick, label, raised }` used identically in Tasks 4,5,7. `PrefillQuery`/`SnapshotActions` query shape `{ queryLocation, queryType, queryTarget? }` consistent across Tasks 6,7. `setShareId(id, shareId)` consistent across Tasks 9,10.
- **No backend changes:** all strings reuse existing `web.text` keys.

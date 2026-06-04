# Query History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-browser query history to the hyperglass landing page — a list of recent successful queries the user can Open (locally-cached output), Share (single-device), Re-run, Re-run with a new target, or Delete.

**Architecture:** History is a frontend feature persisted in `localStorage` via a Zustand `persist` store. Recording happens per-device inside the existing `Result` component (effect keyed on `dataUpdatedAt`). Opening an entry reuses the share-results read-only `Result` snapshot rendering through a newly-extracted `SnapshotResults` component. The only backend changes are config fields: two on `Cache`, one on `Directive`, and new UI strings on `Text`/`Messages`, all projected to the build-time `hyperglass.json`.

**Tech Stack:** Python 3.11 + Pydantic (backend config models); Next.js 13 / React / Chakra UI / Zustand **v3** / React Query v4 / dayjs (frontend); pytest (backend tests); Vitest + jsdom (frontend tests).

**Reference spec:** `docs/superpowers/specs/2026-06-03-query-history-design.md`

**Key environment facts:**
- Zustand is **v5** (`^5.0.8`, migrated in PR #116; this branch is rebased on top of it). The established patterns on main:
  - `import { create } from 'zustand'` and the **curried** call `create<T>()(...)` (note the extra `()`).
  - `withDev` (`util/state.ts`) is typed `StateCreator<T, [], []>`; usage `withDev<T>(creator, 'name')` is unchanged.
  - Custom persist storage: `storage: createJSONStorage(() => historyStorage)` (import `createJSONStorage` from `zustand/middleware`).
  - **Object-returning selectors must be wrapped in `useShallow`** from `zustand/react/shallow` (the v3 `(selector, isEqual)` second-arg form is gone). The new code in this plan uses only single-value selectors, so `useShallow` is not required — but if you combine fields into one selector, wrap it. See `hooks/use-form-state.ts` / `components/looking-glass-form.tsx` for the in-repo pattern.
  - Mirror the existing v5 store in `hyperglass/ui/hooks/use-greeting.ts`; the persist-rehydrate test pattern is in `hooks/use-greeting-rehydrate.test.tsx`.
- `Directive.frontend()` (`hyperglass/models/directive.py:334`) **whitelists** UI-visible fields — a new directive field must be added there explicitly.
- `Params.frontend()` (`hyperglass/models/config/params.py:158`) includes `web` and `messages` wholesale (`"web": ...`, `"messages": ...`), so new `Text`/`Messages` fields reach the UI automatically; only the `cache` include set must be edited.
- Backend attrs are snake_case; `HyperglassModel` camelCases JSON keys. UI config types are written snake_case and run through `CamelCasedProperties`.
- Run a single backend test: `pytest hyperglass/path/test_x.py::test_name -v`
- Run a single UI test: `pnpm --dir ./hyperglass/ui test path/to/file.test.tsx`
- `task lint` (Ruff) and `task ui-lint` (Biome) must be clean; `task ui-typecheck` (tsc) must pass.

---

## File Structure

**Backend (modify):**
- `hyperglass/models/config/cache.py` — add `history_enabled`, `history_limit`.
- `hyperglass/models/config/params.py` — add both to the `frontend()` cache include set.
- `hyperglass/models/directive.py` — add `history: bool = True`; project it in `frontend()`.
- `hyperglass/models/config/web.py` — add history `Text` strings.
- `hyperglass/models/config/messages.py` — add `history_device_unavailable`.

**Backend (tests):**
- `hyperglass/models/config/tests/test_cache.py` (extend)
- `hyperglass/models/config/tests/test_params_frontend.py` (extend)
- `hyperglass/models/tests/test_web.py` (extend)
- `hyperglass/models/tests/test_directive_history.py` (create)

**Frontend (create):**
- `hyperglass/ui/util/history-id.ts` — `makeSubmissionId()`.
- `hyperglass/ui/util/history-storage.ts` — quota-aware `StateStorage`.
- `hyperglass/ui/hooks/use-query-history.ts` — the persist store.
- `hyperglass/ui/hooks/use-record-history.ts` — config-gated recording wrapper.
- `hyperglass/ui/components/results/snapshot-results.tsx` — shared snapshot accordion.
- `hyperglass/ui/components/history/recent-queries.tsx`
- `hyperglass/ui/components/history/history-entry-row.tsx`
- `hyperglass/ui/components/history/history-disabled-hint.tsx`
- `hyperglass/ui/components/history/index.ts`

**Frontend (modify):**
- `hyperglass/ui/types/config.ts` — `_Cache`, `_DirectiveBase`, `_Text`, `_Messages`.
- `hyperglass/ui/types/globals.d.ts` — `ResultSnapshot`, `ShareResponse extends ResultSnapshot`, `force?` already present.
- `hyperglass/ui/hooks/use-form-state.ts` — add `submissionId`, `prefillForm`, extend `reset`.
- `hyperglass/ui/components/results/individual.tsx` — `showShare` prop, snapshot type, recording effect, header hint.
- `hyperglass/ui/pages/result/[id].tsx` — use `SnapshotResults`.
- `hyperglass/ui/pages/index.tsx` — history-open view branch.
- `hyperglass/ui/components/looking-glass-form.tsx` — set `submissionId` on submit; render hint.
- `hyperglass/ui/hooks/index.ts`, `hyperglass/ui/components/index.ts`, `hyperglass/ui/util/index.ts` — re-exports.

**Docs:**
- `docs/...` operator docs + CHANGELOG (Task 24).

---

## Phase 1 — Backend config

### Task 1: Add `history_enabled` / `history_limit` to the Cache model

**Files:**
- Modify: `hyperglass/models/config/cache.py`
- Test: `hyperglass/models/config/tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

Add to `hyperglass/models/config/tests/test_cache.py`:

```python
def test_cache_history_defaults():
    from hyperglass.models.config.cache import Cache

    cache = Cache()
    assert cache.history_enabled is True
    assert cache.history_limit == 10


def test_cache_history_overrides():
    from hyperglass.models.config.cache import Cache

    cache = Cache(history_enabled=False, history_limit=25)
    assert cache.history_enabled is False
    assert cache.history_limit == 25
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest hyperglass/models/config/tests/test_cache.py::test_cache_history_defaults -v`
Expected: FAIL — `Cache` has no attribute `history_enabled`.

- [ ] **Step 3: Add the fields**

In `hyperglass/models/config/cache.py`, append to the `Cache` class body (after `refresh_min_interval`):

```python
    history_enabled: bool = True
    history_limit: int = 10
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest hyperglass/models/config/tests/test_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/models/config/cache.py hyperglass/models/config/tests/test_cache.py
git commit -m "feat(config): add cache.history_enabled and history_limit"
```

---

### Task 2: Project the cache history fields to the frontend

**Files:**
- Modify: `hyperglass/models/config/params.py:163-169` (the `cache` include set in `frontend()`)
- Test: `hyperglass/models/config/tests/test_params_frontend.py`

- [ ] **Step 1: Write the failing test**

Add to `hyperglass/models/config/tests/test_params_frontend.py`:

```python
def test_frontend_includes_cache_history_fields():
    from hyperglass.models.config.params import Params

    fe = Params().frontend()
    assert fe["cache"]["history_enabled"] is True
    assert fe["cache"]["history_limit"] == 10
```

(If the existing tests in this file construct `Params` differently — e.g. with required fixtures — mirror that construction.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest hyperglass/models/config/tests/test_params_frontend.py::test_frontend_includes_cache_history_fields -v`
Expected: FAIL — `KeyError: 'history_enabled'`.

- [ ] **Step 3: Extend the include set**

In `hyperglass/models/config/params.py`, change the `cache` include set inside `frontend()` to:

```python
                "cache": {
                    "show_text",
                    "timeout",
                    "share_enabled",
                    "share_timeout",
                    "refresh_min_interval",
                    "history_enabled",
                    "history_limit",
                },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest hyperglass/models/config/tests/test_params_frontend.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/models/config/params.py hyperglass/models/config/tests/test_params_frontend.py
git commit -m "feat(config): project cache history fields to hyperglass.json"
```

---

### Task 3: Add `history` to the Directive model and project it

**Files:**
- Modify: `hyperglass/models/directive.py` (class body near line 272; `frontend()` near line 337)
- Test: `hyperglass/models/tests/test_directive_history.py` (create)

- [ ] **Step 1: Write the failing test**

Create `hyperglass/models/tests/test_directive_history.py`:

```python
"""Tests for the per-directive history opt-out field."""

from hyperglass.models.directive import Directive


def _directive(**kwargs):
    base = {"id": "test", "name": "Test", "rules": [], "field": None}
    base.update(kwargs)
    return Directive(**base)


def test_directive_history_defaults_true():
    assert _directive().history is True


def test_directive_history_can_be_disabled():
    assert _directive(history=False).history is False


def test_directive_frontend_includes_history():
    fe = _directive(history=False).frontend()
    assert fe["history"] is False

    fe_default = _directive().frontend()
    assert fe_default["history"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest hyperglass/models/tests/test_directive_history.py -v`
Expected: FAIL — `Directive` has no attribute `history`.

- [ ] **Step 3: Add the field and project it**

In `hyperglass/models/directive.py`, add to the `Directive` class body (alongside `multiple`, near line 272):

```python
    history: bool = True
```

Then in `Directive.frontend()`, add `"history"` to the returned `value` dict:

```python
        value = {
            "id": self.id,
            "name": self.name,
            "field_type": self.field_type,
            "groups": self.groups,
            "description": self.field.description if self.field is not None else '',
            "info": None,
            "history": self.history,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest hyperglass/models/tests/test_directive_history.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/models/directive.py hyperglass/models/tests/test_directive_history.py
git commit -m "feat(config): add per-directive history opt-out"
```

---

### Task 4: Add history UI strings to Text and Messages

**Files:**
- Modify: `hyperglass/models/config/web.py` (the `Text` class, after `requery_tooltip` ~line 136)
- Modify: `hyperglass/models/config/messages.py` (the `Messages` class)
- Test: `hyperglass/models/tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Add to `hyperglass/models/tests/test_web.py`:

```python
def test_text_history_string_defaults():
    from hyperglass.models.config.web import Text

    text = Text()
    assert text.history_title == "Recent queries"
    assert text.history_clear_all == "Clear all"
    assert text.history_disabled_hint == "Results for this query type are not saved to history."
    assert text.history_open == "Open"
    assert text.history_delete == "Delete"
```

And add to `hyperglass/models/tests/test_web.py` (or wherever `Messages` is tested; create a small test if none exists):

```python
def test_messages_history_device_unavailable_default():
    from hyperglass.models.config.messages import Messages

    msgs = Messages()
    assert msgs.history_device_unavailable == "The device for this saved query is no longer available."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest hyperglass/models/tests/test_web.py -v`
Expected: FAIL — `Text` has no attribute `history_title`.

- [ ] **Step 3: Add the Text fields**

In `hyperglass/models/config/web.py`, add to the `Text` class (after `requery_tooltip`):

```python
    history_title: str = "Recent queries"
    history_clear_all: str = "Clear all"
    history_clear_confirm: str = "Clear all saved queries?"
    history_back: str = "Back"
    history_open: str = "Open"
    history_share: str = "Share"
    history_rerun: str = "Run again"
    history_new_target: str = "Run with a new target"
    history_delete: str = "Delete"
    history_disabled_hint: str = "Results for this query type are not saved to history."
```

- [ ] **Step 4: Add the Messages field**

In `hyperglass/models/config/messages.py`, add to the `Messages` class (mirror the existing `Field(...)` style):

```python
    history_device_unavailable: str = Field(
        "The device for this saved query is no longer available.",
        title="History Device Unavailable",
        description="Displayed when re-running a saved query whose device no longer exists.",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest hyperglass/models/tests/test_web.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/models/config/web.py hyperglass/models/config/messages.py hyperglass/models/tests/test_web.py
git commit -m "feat(config): add query-history UI strings"
```

---

## Phase 2 — UI types

### Task 5: Extend UI config types

**Files:**
- Modify: `hyperglass/ui/types/config.ts` (`_Cache` ~149, `_DirectiveBase` ~114, `_Text` ~25, `_Messages` ~8)

No unit test — validated by `task ui-typecheck` after consumers exist. This task is a prerequisite; typecheck is exercised in later tasks.

- [ ] **Step 1: Add the fields**

`_Cache` (after `refresh_min_interval`):

```ts
  history_enabled: boolean;
  history_limit: number;
```

`_DirectiveBase` (after `info`):

```ts
  history: boolean;
```

`_Text` (after `requery_tooltip`):

```ts
  history_title: string;
  history_clear_all: string;
  history_clear_confirm: string;
  history_back: string;
  history_open: string;
  history_share: string;
  history_rerun: string;
  history_new_target: string;
  history_delete: string;
  history_disabled_hint: string;
```

`_Messages` (after `no_output`):

```ts
  history_device_unavailable: string;
```

- [ ] **Step 2: Verify typecheck still passes**

Run: `pnpm --dir ./hyperglass/ui typecheck` (or `task ui-typecheck`)
Expected: PASS (no consumers yet, so no errors).

- [ ] **Step 3: Commit**

```bash
git add hyperglass/ui/types/config.ts
git commit -m "feat(ui): add query-history fields to config types"
```

---

### Task 6: Add the `ResultSnapshot` type and base `ShareResponse` on it

**Files:**
- Modify: `hyperglass/ui/types/globals.d.ts`

- [ ] **Step 1: Inspect the current `ShareResponse`**

Run: `grep -n "ShareResponse\|QueryResponse\|ResponseLevel" hyperglass/ui/types/globals.d.ts`
Note the exact current shape of `ShareResponse` and `QueryResponse` so the new interface matches their field types.

- [ ] **Step 2: Add `ResultSnapshot` and re-base `ShareResponse`**

In `hyperglass/ui/types/globals.d.ts`, add:

```ts
interface ResultSnapshot {
  id: string;
  output: QueryResponse['output'];
  format: QueryResponse['format'];
  level: ResponseLevel;
  timestamp: string;
  runtime: number;
  cached: boolean;
  keywords: string[];
  queryLabels: { location: string };
}
```

Then change the existing `ShareResponse` declaration so it extends `ResultSnapshot`, keeping its share-only fields (`shared`, `query`, `createdAt`, `expiresAt`, and any others currently present). If `ShareResponse` currently re-declares fields now in `ResultSnapshot`, remove those duplicates and rely on the `extends`. Example shape (adapt to the real one found in Step 1):

```ts
interface ShareResponse extends ResultSnapshot {
  shared: boolean;
  query: SimpleQuery;          // keep the existing query type name
  createdAt: string;
  expiresAt: string;
}
```

- [ ] **Step 3: Verify typecheck passes**

Run: `pnpm --dir ./hyperglass/ui typecheck`
Expected: PASS. If `ShareResponse` consumers break, it means a field type drifted — align `ResultSnapshot` to the real `QueryResponse`/`ShareResponse` types.

- [ ] **Step 4: Commit**

```bash
git add hyperglass/ui/types/globals.d.ts
git commit -m "feat(ui): add ResultSnapshot type, re-base ShareResponse"
```

---

## Phase 3 — History store

### Task 7: Submission-id utility

**Files:**
- Create: `hyperglass/ui/util/history-id.ts`
- Modify: `hyperglass/ui/util/index.ts` (re-export)
- Test: `hyperglass/ui/util/history-id.test.ts` (create)

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/util/history-id.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { makeSubmissionId } from './history-id';

describe('makeSubmissionId', () => {
  it('returns a non-empty string', () => {
    expect(typeof makeSubmissionId()).toBe('string');
    expect(makeSubmissionId().length).toBeGreaterThan(0);
  });

  it('returns unique values across calls', () => {
    const ids = new Set(Array.from({ length: 100 }, () => makeSubmissionId()));
    expect(ids.size).toBe(100);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test util/history-id.test.ts`
Expected: FAIL — cannot find module `./history-id`.

- [ ] **Step 3: Implement**

Create `hyperglass/ui/util/history-id.ts`:

```ts
/**
 * Generate a unique submission id. Prefers crypto.randomUUID, with a fallback
 * for environments that lack it.
 */
export function makeSubmissionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
```

Add to `hyperglass/ui/util/index.ts`:

```ts
export * from './history-id';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test util/history-id.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/util/history-id.ts hyperglass/ui/util/index.ts hyperglass/ui/util/history-id.test.ts
git commit -m "feat(ui): add makeSubmissionId util"
```

---

### Task 8: Quota-aware storage adapter

**Files:**
- Create: `hyperglass/ui/util/history-storage.ts`
- Test: `hyperglass/ui/util/history-storage.test.ts` (create)

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/util/history-storage.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { shrinkSerialized } from './history-storage';

const make = (entries: unknown[]) =>
  JSON.stringify({ state: { entries }, version: 1 });

describe('shrinkSerialized', () => {
  it('strips output from the oldest entry that still has one', () => {
    const serialized = make([
      { id: 'new', results: { d1: { output: 'A' } } },
      { id: 'old', results: { d1: { output: 'B' } } },
    ]);
    const out = JSON.parse(shrinkSerialized(serialized) as string);
    // oldest (last) entry stripped first
    expect('output' in out.state.entries[1].results.d1).toBe(false);
    expect(out.state.entries[0].results.d1.output).toBe('A');
  });

  it('drops the oldest entry once no outputs remain to strip', () => {
    const serialized = make([
      { id: 'new', results: { d1: {} } },
      { id: 'old', results: { d1: {} } },
    ]);
    const out = JSON.parse(shrinkSerialized(serialized) as string);
    expect(out.state.entries).toHaveLength(1);
    expect(out.state.entries[0].id).toBe('new');
  });

  it('returns null when nothing remains', () => {
    expect(shrinkSerialized(make([]))).toBeNull();
    expect(shrinkSerialized('not json')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test util/history-storage.test.ts`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement**

Create `hyperglass/ui/util/history-storage.ts`:

```ts
import type { StateStorage } from 'zustand/middleware';

/**
 * Incrementally shrink a serialized persisted-history blob to fit under the
 * localStorage quota: first strip `output` from the oldest entry that still has
 * one, then (when no outputs remain) drop the oldest entry. Returns the new
 * serialized string, or null when nothing remains / input is unparseable.
 */
export function shrinkSerialized(serialized: string): string | null {
  let parsed: { state?: { entries?: unknown[] } };
  try {
    parsed = JSON.parse(serialized);
  } catch {
    return null;
  }
  const entries = parsed?.state?.entries;
  if (!Array.isArray(entries) || entries.length === 0) {
    return null;
  }
  // Entries are stored newest-first, so the oldest is at the end.
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i] as { results?: Record<string, { output?: unknown }> };
    const results = entry.results ?? {};
    for (const key of Object.keys(results)) {
      if (results[key] && 'output' in results[key]) {
        delete results[key].output;
        return JSON.stringify(parsed);
      }
    }
  }
  entries.pop();
  return JSON.stringify(parsed);
}

/**
 * A zustand v3 StateStorage backed by localStorage that never throws: reads and
 * writes are guarded, and a QuotaExceededError on write triggers incremental
 * shrink-and-retry via shrinkSerialized.
 */
export const historyStorage: StateStorage = {
  getItem(name: string): string | null {
    try {
      return typeof window === 'undefined' ? null : window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem(name: string, value: string): void {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(name, value);
      return;
    } catch {
      let current: string | null = value;
      // Shrink until it fits or there is nothing left to store.
      while (current !== null) {
        current = shrinkSerialized(current);
        if (current === null) {
          try {
            window.localStorage.removeItem(name);
          } catch {
            /* ignore */
          }
          return;
        }
        try {
          window.localStorage.setItem(name, current);
          return;
        } catch {
          /* keep shrinking */
        }
      }
    }
  },
  removeItem(name: string): void {
    try {
      if (typeof window !== 'undefined') window.localStorage.removeItem(name);
    } catch {
      /* ignore */
    }
  },
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test util/history-storage.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/util/history-storage.ts hyperglass/ui/util/history-storage.test.ts
git commit -m "feat(ui): add quota-aware history storage adapter"
```

---

### Task 9: The query-history store

**Files:**
- Create: `hyperglass/ui/hooks/use-query-history.ts`
- Modify: `hyperglass/ui/hooks/index.ts` (re-export)
- Test: `hyperglass/ui/hooks/use-query-history.test.ts` (create)

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/hooks/use-query-history.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useQueryHistory } from './use-query-history';
import type { RecordInput } from './use-query-history';

const snapshot = (output: string) => ({
  id: 'cache-1',
  output,
  format: 'text/plain',
  level: 'success',
  timestamp: 'now',
  runtime: 1,
  cached: false,
  keywords: [],
  queryLabels: { location: 'Core 1' },
});

const input = (over: Partial<RecordInput> = {}): RecordInput => ({
  submissionId: 's1',
  deviceId: 'core1',
  deviceLabel: 'Core 1',
  query: { queryType: 'bgp_route', queryTarget: ['8.8.8.0/24'] },
  labels: { type: 'BGP Route', target: '8.8.8.0/24' },
  snapshot: snapshot('A'),
  limit: 10,
  ...over,
});

beforeEach(() => {
  useQueryHistory.setState({ entries: [], openId: null });
  window.localStorage.clear();
});

describe('useQueryHistory.record', () => {
  it('creates an entry keyed by submissionId', () => {
    useQueryHistory.getState().record(input());
    const { entries } = useQueryHistory.getState();
    expect(entries).toHaveLength(1);
    expect(entries[0].id).toBe('s1');
    expect(entries[0].results.core1.output).toBe('A');
    expect(entries[0].query.queryLocation).toEqual(['core1']);
  });

  it('groups multiple devices of the same submission into one entry', () => {
    useQueryHistory.getState().record(input());
    useQueryHistory.getState().record(
      input({ deviceId: 'edge2', deviceLabel: 'Edge 2', snapshot: snapshot('B') }),
    );
    const { entries } = useQueryHistory.getState();
    expect(entries).toHaveLength(1);
    expect(Object.keys(entries[0].results).sort()).toEqual(['core1', 'edge2']);
    expect(entries[0].query.queryLocation.sort()).toEqual(['core1', 'edge2']);
  });

  it('keeps distinct submissions as separate entries, newest first', () => {
    useQueryHistory.getState().record(input({ submissionId: 's1' }));
    useQueryHistory.getState().record(input({ submissionId: 's2' }));
    const { entries } = useQueryHistory.getState();
    expect(entries.map(e => e.id)).toEqual(['s2', 's1']);
  });

  it('enforces the limit, evicting oldest', () => {
    for (let i = 0; i < 12; i++) {
      useQueryHistory.getState().record(input({ submissionId: `s${i}`, limit: 10 }));
    }
    const { entries } = useQueryHistory.getState();
    expect(entries).toHaveLength(10);
    expect(entries[0].id).toBe('s11');
    expect(entries.find(e => e.id === 's0')).toBeUndefined();
  });
});

describe('useQueryHistory remove/clear/open/close', () => {
  it('remove deletes by id', () => {
    useQueryHistory.getState().record(input({ submissionId: 's1' }));
    useQueryHistory.getState().record(input({ submissionId: 's2' }));
    useQueryHistory.getState().remove('s1');
    expect(useQueryHistory.getState().entries.map(e => e.id)).toEqual(['s2']);
  });

  it('clear empties entries', () => {
    useQueryHistory.getState().record(input());
    useQueryHistory.getState().clear();
    expect(useQueryHistory.getState().entries).toHaveLength(0);
  });

  it('open/close set and reset openId', () => {
    useQueryHistory.getState().open('s1');
    expect(useQueryHistory.getState().openId).toBe('s1');
    useQueryHistory.getState().close();
    expect(useQueryHistory.getState().openId).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-query-history.test.ts`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement the store**

Create `hyperglass/ui/hooks/use-query-history.ts`:

```ts
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { historyStorage } from '~/util/history-storage';
import { withDev } from '~/util';

export interface ResultSnapshotData {
  id: string;
  output: QueryResponse['output'];
  format: QueryResponse['format'];
  level: ResponseLevel;
  timestamp: string;
  runtime: number;
  cached: boolean;
  keywords: string[];
  queryLabels: { location: string };
}

export interface HistoryEntry {
  id: string;
  savedAt: number;
  query: { queryLocation: string[]; queryType: string; queryTarget: string[] };
  labels: { locations: string[]; type: string; target: string };
  results: Record<string, ResultSnapshotData>;
}

export interface RecordInput {
  submissionId: string;
  deviceId: string;
  deviceLabel: string;
  query: { queryType: string; queryTarget: string[] };
  labels: { type: string; target: string };
  snapshot: ResultSnapshotData;
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
      partialize: state => ({ entries: state.entries }),
    },
  ),
);
```

Add to `hyperglass/ui/hooks/index.ts`:

```ts
export * from './use-query-history';
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-query-history.test.ts`
Expected: PASS.

- [ ] **Step 5: Typecheck**

Run: `pnpm --dir ./hyperglass/ui typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hyperglass/ui/hooks/use-query-history.ts hyperglass/ui/hooks/index.ts hyperglass/ui/hooks/use-query-history.test.ts
git commit -m "feat(ui): add useQueryHistory persist store"
```

---

### Task 10: Config-gated recording wrapper hook

**Files:**
- Create: `hyperglass/ui/hooks/use-record-history.ts`
- Modify: `hyperglass/ui/hooks/index.ts`
- Test: `hyperglass/ui/hooks/use-record-history.test.tsx` (create)

The hook returns a stable callback that records only when the global switch and the directive flag both allow it.

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/hooks/use-record-history.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useRecordHistory } from './use-record-history';
import { useQueryHistory } from './use-query-history';

const recordSpy = vi.fn();

vi.mock('~/context', () => ({
  useConfig: () => ({ cache: { historyEnabled: true, historyLimit: 10 } }),
}));

beforeEach(() => {
  recordSpy.mockClear();
  useQueryHistory.setState({
    entries: [],
    openId: null,
    record: recordSpy,
  } as never);
});

const payload = {
  submissionId: 's1',
  deviceId: 'core1',
  deviceLabel: 'Core 1',
  directiveHistory: true,
  query: { queryType: 'bgp_route', queryTarget: ['x'] },
  labels: { type: 'BGP Route', target: 'x' },
  snapshot: {} as never,
};

describe('useRecordHistory', () => {
  it('records when global + directive both allow it', () => {
    const { result } = renderHook(() => useRecordHistory());
    result.current(payload);
    expect(recordSpy).toHaveBeenCalledOnce();
    expect(recordSpy.mock.calls[0][0].limit).toBe(10);
  });

  it('no-ops when the directive opts out', () => {
    const { result } = renderHook(() => useRecordHistory());
    result.current({ ...payload, directiveHistory: false });
    expect(recordSpy).not.toHaveBeenCalled();
  });
});
```

(If `cache` is consumed as `cache.historyEnabled`/`cache.historyLimit` via `useConfig()`, the mock above reflects the camelCased runtime shape.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-record-history.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement**

Create `hyperglass/ui/hooks/use-record-history.ts`:

```ts
import { useCallback } from 'react';
import { useConfig } from '~/context';
import { useQueryHistory } from './use-query-history';
import type { ResultSnapshotData } from './use-query-history';

interface RecordHistoryArgs {
  submissionId: string;
  deviceId: string;
  deviceLabel: string;
  directiveHistory: boolean;
  query: { queryType: string; queryTarget: string[] };
  labels: { type: string; target: string };
  snapshot: ResultSnapshotData;
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
```

Add to `hyperglass/ui/hooks/index.ts`:

```ts
export * from './use-record-history';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-record-history.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/hooks/use-record-history.ts hyperglass/ui/hooks/index.ts hyperglass/ui/hooks/use-record-history.test.tsx
git commit -m "feat(ui): add config-gated useRecordHistory hook"
```

---

## Phase 4 — Result / SnapshotResults refactor

### Task 11: Decouple `readOnly`, add `showShare`, retype `snapshot`

**Files:**
- Modify: `hyperglass/ui/components/results/individual.tsx` (props ~42-49; share render line 294; snapshot type)
- Test: `hyperglass/ui/components/results/individual.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/components/results/individual.test.tsx`. (Mirror the rendering/provider setup used in `hyperglass/ui/components/looking-glass-form.test.tsx` for `useConfig`/Chakra; reuse its test harness/wrapper.)

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Accordion } from '@chakra-ui/react';
// import the shared test wrapper used elsewhere (provides Chakra + config context)
import { TestWrapper } from '~/test/wrapper'; // adjust to the actual shared helper
import { Result } from './individual';

const snapshot = {
  id: 'cache-1',
  output: 'hello',
  format: 'text/plain',
  level: 'success',
  timestamp: 'now',
  runtime: 1,
  cached: true,
  keywords: [],
  queryLabels: { location: 'Core 1' },
} as never;

const renderResult = (props: Record<string, unknown>) =>
  render(
    <TestWrapper>
      <Accordion>
        <Result index={0} queryLocation="core1" snapshot={snapshot} {...props} />
      </Accordion>
    </TestWrapper>,
  );

describe('Result share visibility', () => {
  it('hides Share when readOnly and showShare not set', () => {
    renderResult({ readOnly: true });
    expect(screen.queryByText('Share')).not.toBeInTheDocument();
  });

  it('shows Share in history mode (readOnly + showShare)', () => {
    renderResult({ readOnly: true, showShare: true });
    expect(screen.getByText('Share')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test components/results/individual.test.tsx`
Expected: FAIL — `showShare` does nothing yet (the second assertion fails).

- [ ] **Step 3: Implement**

In `hyperglass/ui/components/results/individual.tsx`:

Change the props interface:

```ts
interface ResultProps {
  index: number;
  queryLocation: string;
  /** Snapshot (share link or local history) — skips the live LG query and renders directly. */
  snapshot?: ResultSnapshot;
  /** When true, hides the RequeryButton (read-only views). */
  readOnly?: boolean;
  /** Controls ShareButton visibility; defaults to !readOnly. */
  showShare?: boolean;
}
```

Destructure with a default:

```ts
  const { index, queryLocation, snapshot, readOnly = false, showShare = !readOnly } = props;
```

Change the share-button render (currently `{!readOnly && data?.id && <ShareButton cacheId={data.id} />}`) to:

```tsx
          {showShare && data?.id && <ShareButton cacheId={data.id} />}
```

(`snapshotAsQueryResponse` already reads only fields present on `ResultSnapshot`, so the type change is safe.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test components/results/individual.test.tsx`
Expected: PASS.

- [ ] **Step 5: Verify the share page is unaffected**

Run: `pnpm --dir ./hyperglass/ui typecheck`
Expected: PASS. `pages/result/[id].tsx` passes `readOnly` only → `showShare` defaults to `false` → Share stays hidden there (unchanged behavior).

- [ ] **Step 6: Commit**

```bash
git add hyperglass/ui/components/results/individual.tsx hyperglass/ui/components/results/individual.test.tsx
git commit -m "feat(ui): decouple Result readOnly/showShare; retype snapshot"
```

---

### Task 12: Extract `SnapshotResults` and use it on the share page

**Files:**
- Create: `hyperglass/ui/components/results/snapshot-results.tsx`
- Modify: `hyperglass/ui/components/results/index.ts` (export)
- Modify: `hyperglass/ui/pages/result/[id].tsx` (use the component)
- Test: `hyperglass/ui/components/results/snapshot-results.test.tsx` (create)

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/components/results/snapshot-results.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TestWrapper } from '~/test/wrapper'; // adjust to the actual shared helper
import { SnapshotResults } from './snapshot-results';

const snap = (location: string, output: string) =>
  ({
    id: `c-${location}`,
    output,
    format: 'text/plain',
    level: 'success',
    timestamp: 'now',
    runtime: 1,
    cached: true,
    keywords: [],
    queryLabels: { location },
  }) as never;

describe('SnapshotResults', () => {
  it('renders one result per item', () => {
    render(
      <TestWrapper>
        <SnapshotResults
          items={[
            { queryLocation: 'core1', snapshot: snap('Core 1', 'A') },
            { queryLocation: 'edge2', snapshot: snap('Edge 2', 'B') },
          ]}
        />
      </TestWrapper>,
    );
    expect(screen.getByText('Core 1')).toBeInTheDocument();
    expect(screen.getByText('Edge 2')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test components/results/snapshot-results.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement `SnapshotResults`**

Create `hyperglass/ui/components/results/snapshot-results.tsx` (mirrors the markup currently inline in `pages/result/[id].tsx`):

```tsx
import { Accordion } from '@chakra-ui/react';
import { AnimatedDiv } from '~/elements';
import { Result } from './individual';

export interface SnapshotResultsItem {
  queryLocation: string;
  snapshot: ResultSnapshot;
}

interface SnapshotResultsProps {
  items: SnapshotResultsItem[];
  /** Show each result's ShareButton (history-open); default false (share page). */
  showShare?: boolean;
}

export const SnapshotResults = (props: SnapshotResultsProps): JSX.Element => {
  const { items, showShare = false } = props;
  return (
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
      maxW={{ base: '100%', md: '75%' }}
    >
      <Accordion defaultIndex={items.map((_, i) => i)} allowMultiple>
        {items.map((item, index) => (
          <Result
            key={item.queryLocation}
            index={index}
            queryLocation={item.queryLocation}
            snapshot={item.snapshot}
            readOnly
            showShare={showShare}
          />
        ))}
      </Accordion>
    </AnimatedDiv>
  );
};
```

Add to `hyperglass/ui/components/results/index.ts`:

```ts
export * from './snapshot-results';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test components/results/snapshot-results.test.tsx`
Expected: PASS.

- [ ] **Step 5: Refactor the share page to use it**

In `hyperglass/ui/pages/result/[id].tsx`, replace the inline `AnimatedDiv`/`Accordion`/`Result` block with:

```tsx
        <SnapshotResults items={[{ queryLocation: snapshot.query.query_location, snapshot }]} />
```

Add the import: `import { SnapshotResults } from '~/components/results/snapshot-results';` and drop the now-unused `Accordion`/`AnimatedDiv` imports if they are no longer referenced.

- [ ] **Step 6: Verify the share page still works**

Run: `pnpm --dir ./hyperglass/ui test pages/result` and `pnpm --dir ./hyperglass/ui typecheck`
Expected: PASS (existing share-page tests still green).

- [ ] **Step 7: Commit**

```bash
git add hyperglass/ui/components/results/snapshot-results.tsx hyperglass/ui/components/results/index.ts hyperglass/ui/pages/result/\[id\].tsx hyperglass/ui/components/results/snapshot-results.test.tsx
git commit -m "refactor(ui): extract SnapshotResults; reuse on share page"
```

---

## Phase 5 — Form state: submissionId + prefillForm

### Task 13: Add `submissionId` to the form store

**Files:**
- Modify: `hyperglass/ui/hooks/use-form-state.ts` (state shape, `reset`, a setter)
- Test: `hyperglass/ui/hooks/use-form-state.test.ts` (create if absent)

- [ ] **Step 1: Write the failing test**

Create/append `hyperglass/ui/hooks/use-form-state.test.ts`:

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { useFormState } from './use-form-state';

beforeEach(async () => {
  await useFormState.getState().reset();
});

describe('useFormState.submissionId', () => {
  it('defaults to null and can be set', () => {
    expect(useFormState.getState().submissionId).toBeNull();
    useFormState.getState().setSubmissionId('abc');
    expect(useFormState.getState().submissionId).toBe('abc');
  });

  it('is cleared by reset', async () => {
    useFormState.getState().setSubmissionId('abc');
    await useFormState.getState().reset();
    expect(useFormState.getState().submissionId).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-form-state.test.ts`
Expected: FAIL — `submissionId` is undefined / `setSubmissionId` missing.

- [ ] **Step 3: Implement**

In `hyperglass/ui/hooks/use-form-state.ts`:

Add to `FormStateType` (interface):

```ts
  submissionId: string | null;
  setSubmissionId(value: string | null): void;
```

Add to the initial state object (alongside `status`, `target`):

```ts
  submissionId: null,
```

Add the setter (alongside the other methods):

```ts
  setSubmissionId(submissionId: string | null): void {
    set({ submissionId });
  },
```

Add `submissionId: null,` to the object passed to `set({...})` inside `reset()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-form-state.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/hooks/use-form-state.ts hyperglass/ui/hooks/use-form-state.test.ts
git commit -m "feat(ui): track submissionId in form state"
```

---

### Task 14: Extract `prefillForm` from `locationChange`

**Files:**
- Modify: `hyperglass/ui/hooks/use-form-state.ts`
- Test: `hyperglass/ui/hooks/use-form-state.test.ts` (extend)

`prefillForm` sets `form`, `selections`, and `filtered` for a given query without touching react-hook-form. `locationChange`'s directive-intersection computation is the reusable core.

- [ ] **Step 1: Write the failing test**

Append to `hyperglass/ui/hooks/use-form-state.test.ts`:

```ts
import type { Device } from '~/types';

const device = (id: string): Device =>
  ({
    id,
    name: id.toUpperCase(),
    directives: [{ id: 'bgp_route', name: 'BGP Route', groups: ['ip'] } as never],
  }) as Device;

describe('useFormState.prefillForm', () => {
  it('sets form values and selections for valid locations', () => {
    const getDevice = (id: string) => (id === 'core1' ? device('core1') : null);
    useFormState.getState().prefillForm(
      { queryLocation: ['core1'], queryType: 'bgp_route', queryTarget: ['8.8.8.0/24'] },
      getDevice as never,
    );
    const state = useFormState.getState();
    expect(state.form.queryLocation).toEqual(['core1']);
    expect(state.form.queryType).toBe('bgp_route');
    expect(state.form.queryTarget).toEqual(['8.8.8.0/24']);
    expect(state.selections.queryLocation.map(o => o.value)).toEqual(['core1']);
  });

  it('drops unknown devices and returns the valid subset', () => {
    const getDevice = (id: string) => (id === 'core1' ? device('core1') : null);
    const valid = useFormState.getState().prefillForm(
      { queryLocation: ['core1', 'ghost'], queryType: 'bgp_route', queryTarget: ['x'] },
      getDevice as never,
    );
    expect(valid).toEqual(['core1']);
    expect(useFormState.getState().form.queryLocation).toEqual(['core1']);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-form-state.test.ts`
Expected: FAIL — `prefillForm` is not a function.

- [ ] **Step 3: Implement `prefillForm`**

In `hyperglass/ui/hooks/use-form-state.ts`, add to `FormStateType`:

```ts
  prefillForm(
    query: { queryLocation: string[]; queryType: string; queryTarget: string[] },
    getDevice: UseDeviceReturn,
  ): string[];
```

Implement it (reusing the intersection logic that `locationChange` already performs — `intersectionWith`, `dedupObjectArray` are already imported in this file):

```ts
  prefillForm(query, getDevice): string[] {
    const validDevices = query.queryLocation
      .map(getDevice)
      .filter((device): device is Device => device !== null);
    const validLocations = validDevices.map(d => d.id);

    const allGroups = validDevices.map(dev =>
      Array.from(new Set(dev.directives.flatMap(dir => dir.groups))),
    );
    const intersecting = validDevices.length ? intersectionWith(...allGroups, isEqual) : [];
    const allDirectives = validDevices.map(device => device.directives);
    const intersectingDirectives = validDevices.length
      ? intersectionWith(...allDirectives, isEqual)
      : [];
    const directives = dedupObjectArray(intersectingDirectives, 'id');

    set({
      form: {
        queryLocation: validLocations,
        queryType: query.queryType,
        queryTarget: query.queryTarget,
      },
      selections: {
        queryLocation: validDevices.map(d => ({ value: d.id, label: d.name })),
        queryType: null,
      },
      filtered: { groups: intersecting, types: directives },
      target: { display: query.queryTarget.join(' ') },
    });

    return validLocations;
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test hooks/use-form-state.test.ts`
Expected: PASS.

- [ ] **Step 5: Sanity-check the form still works**

Run: `pnpm --dir ./hyperglass/ui test components/looking-glass-form.test.tsx`
Expected: PASS (we added a method; `locationChange` is unchanged).

- [ ] **Step 6: Commit**

```bash
git add hyperglass/ui/hooks/use-form-state.ts hyperglass/ui/hooks/use-form-state.test.ts
git commit -m "feat(ui): add prefillForm to form state"
```

---

## Phase 6 — Recording wiring

### Task 15: Record successful results from `Result`

**Files:**
- Modify: `hyperglass/ui/components/results/individual.tsx`
- Test: `hyperglass/ui/components/results/individual.test.tsx` (extend)

- [ ] **Step 1: Write the failing test**

Append to `hyperglass/ui/components/results/individual.test.tsx` a test that asserts recording fires for a successful **live** result and is skipped for snapshot renders. Use a spy on `useRecordHistory`:

```tsx
import { vi } from 'vitest';

const recordFn = vi.fn();
vi.mock('~/hooks/use-record-history', () => ({
  useRecordHistory: () => recordFn,
}));

// Within a describe block, after configuring useLGQuery to return a successful
// live result for queryLocation 'core1' (mirror the mocking already used in
// use-lg-query.test.tsx), assert:
//   expect(recordFn).toHaveBeenCalledWith(expect.objectContaining({ deviceId: 'core1' }));
// And for a snapshot render: expect(recordFn).not.toHaveBeenCalled();
```

(Implement the concrete `useLGQuery` mock by mirroring `hyperglass/ui/hooks/use-lg-query.test.tsx`; the key assertions are the two `recordFn` expectations.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test components/results/individual.test.tsx`
Expected: FAIL — recording not wired.

- [ ] **Step 3: Implement the recording effect**

In `hyperglass/ui/components/results/individual.tsx`:

Add imports:

```ts
import { useRecordHistory } from '~/hooks';
```

Inside `_Result`, after the existing hooks, derive the directive and recorder:

```ts
  const recordHistory = useRecordHistory();
  const getDirective = useFormState(s => s.getDirective);
  const submissionId = useFormState(s => s.submissionId);
```

Add the recording effect (place it after the `data` is resolved, near the other effects):

```ts
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
          keywords: data.keywords,
          queryLabels: { location: device.name },
        },
      });
    }
    // dataUpdatedAt advances on every settle (fresh or cache-served); submissionId
    // changes per submit. Both are sufficient to capture each run exactly once.
  }, [dataUpdatedAt, submissionId]); // eslint-disable-line react-hooks/exhaustive-deps
```

(`historyEnabled` gating lives inside `useRecordHistory`; the directive flag is passed through.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test components/results/individual.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/results/individual.tsx hyperglass/ui/components/results/individual.test.tsx
git commit -m "feat(ui): record successful results into query history"
```

---

### Task 16: Generate a `submissionId` on submit

**Files:**
- Modify: `hyperglass/ui/components/looking-glass-form.tsx` (`submitHandler`)
- Test: covered indirectly; add an assertion to `components/looking-glass-form.test.tsx` if it already exercises submit.

- [ ] **Step 1: Implement**

In `hyperglass/ui/components/looking-glass-form.tsx`:

Add imports / selectors:

```ts
import { makeSubmissionId } from '~/util';
```
```ts
  const setSubmissionId = useFormState(s => s.setSubmissionId);
```

In `submitHandler`, set a fresh id immediately before transitioning to results (both the non-FQDN `setStatus('results')` branch and the FQDN `resolvedOpen()` branch should run after assigning it). The simplest correct placement is right after the greeting check passes:

```ts
    // Stamp this submission so its per-device results group into one history entry.
    setSubmissionId(makeSubmissionId());
```

- [ ] **Step 2: Verify build/typecheck and form test**

Run: `pnpm --dir ./hyperglass/ui test components/looking-glass-form.test.tsx && pnpm --dir ./hyperglass/ui typecheck`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add hyperglass/ui/components/looking-glass-form.tsx
git commit -m "feat(ui): stamp submissionId on query submit"
```

---

## Phase 7 — History UI

### Task 17: `HistoryDisabledHint`

**Files:**
- Create: `hyperglass/ui/components/history/history-disabled-hint.tsx`
- Create: `hyperglass/ui/components/history/index.ts`
- Modify: `hyperglass/ui/components/index.ts` (re-export history barrel)
- Test: `hyperglass/ui/components/history/history-disabled-hint.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/components/history/history-disabled-hint.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TestWrapper } from '~/test/wrapper'; // adjust to actual shared helper
import { HistoryDisabledHint } from './history-disabled-hint';

// TestWrapper provides useConfig with cache.historyEnabled true and
// web.text.historyDisabledHint set to a known string.

describe('HistoryDisabledHint', () => {
  it('renders when global history on and directive opts out', () => {
    render(
      <TestWrapper>
        <HistoryDisabledHint directiveHistory={false} />
      </TestWrapper>,
    );
    expect(screen.getByLabelText(/not saved to history/i)).toBeInTheDocument();
  });

  it('renders nothing when the directive allows history', () => {
    const { container } = render(
      <TestWrapper>
        <HistoryDisabledHint directiveHistory={true} />
      </TestWrapper>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test components/history/history-disabled-hint.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement**

Create `hyperglass/ui/components/history/history-disabled-hint.tsx`:

```tsx
import { Box, Tooltip } from '@chakra-ui/react';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';

interface HistoryDisabledHintProps {
  directiveHistory: boolean;
}

export const HistoryDisabledHint = (props: HistoryDisabledHintProps): JSX.Element | null => {
  const { directiveHistory } = props;
  const { cache, web } = useConfig();

  if (!cache.historyEnabled || directiveHistory) {
    return null;
  }

  return (
    <Tooltip hasArrow label={web.text.historyDisabledHint} placement="top">
      <Box as="span" aria-label={web.text.historyDisabledHint} display="inline-flex">
        <DynamicIcon icon={{ fi: 'FiEyeOff' }} boxSize="14px" />
      </Box>
    </Tooltip>
  );
};
```

Create `hyperglass/ui/components/history/index.ts`:

```ts
export * from './history-disabled-hint';
```

Add to `hyperglass/ui/components/index.ts`:

```ts
export * from './history';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test components/history/history-disabled-hint.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/history/ hyperglass/ui/components/index.ts
git commit -m "feat(ui): add HistoryDisabledHint component"
```

---

### Task 18: `HistoryEntryRow`

**Files:**
- Create: `hyperglass/ui/components/history/history-entry-row.tsx`
- Modify: `hyperglass/ui/components/history/index.ts`
- Test: `hyperglass/ui/components/history/history-entry-row.test.tsx`

The row reads everything it needs from the entry and calls store/form actions. `getDevice` comes from `useDevice()`.

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/components/history/history-entry-row.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TestWrapper } from '~/test/wrapper'; // adjust to actual shared helper
import { HistoryEntryRow } from './history-entry-row';
import { useQueryHistory } from '~/hooks';
import type { HistoryEntry } from '~/hooks/use-query-history';

const baseSnap = {
  id: 'cache-1',
  output: 'x',
  format: 'text/plain',
  level: 'success',
  timestamp: 'now',
  runtime: 1,
  cached: true,
  keywords: [],
  queryLabels: { location: 'Core 1' },
};

const singleEntry: HistoryEntry = {
  id: 's1',
  savedAt: Date.now(),
  query: { queryLocation: ['core1'], queryType: 'bgp_route', queryTarget: ['8.8.8.0/24'] },
  labels: { locations: ['Core 1'], type: 'BGP Route', target: '8.8.8.0/24' },
  results: { core1: baseSnap as never },
};

const multiEntry: HistoryEntry = {
  ...singleEntry,
  id: 's2',
  query: { ...singleEntry.query, queryLocation: ['core1', 'edge2'] },
  labels: { ...singleEntry.labels, locations: ['Core 1', 'Edge 2'] },
  results: { core1: baseSnap as never, edge2: baseSnap as never },
};

beforeEach(() => {
  useQueryHistory.setState({ entries: [singleEntry, multiEntry], openId: null });
});

describe('HistoryEntryRow', () => {
  it('shows the Share icon for single-device entries', () => {
    render(<TestWrapper><HistoryEntryRow entry={singleEntry} /></TestWrapper>);
    expect(screen.getByLabelText('Share')).toBeInTheDocument();
  });

  it('hides the Share icon for multi-device entries', () => {
    render(<TestWrapper><HistoryEntryRow entry={multiEntry} /></TestWrapper>);
    expect(screen.queryByLabelText('Share')).not.toBeInTheDocument();
  });

  it('Open sets openId', () => {
    render(<TestWrapper><HistoryEntryRow entry={singleEntry} /></TestWrapper>);
    fireEvent.click(screen.getByLabelText('Open'));
    expect(useQueryHistory.getState().openId).toBe('s1');
  });

  it('Delete removes the entry', () => {
    render(<TestWrapper><HistoryEntryRow entry={singleEntry} /></TestWrapper>);
    fireEvent.click(screen.getByLabelText('Delete'));
    expect(useQueryHistory.getState().entries.find(e => e.id === 's1')).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test components/history/history-entry-row.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement**

Create `hyperglass/ui/components/history/history-entry-row.tsx`:

```tsx
import { Button, Flex, HStack, Text, Tooltip, useToast } from '@chakra-ui/react';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';
import { useDevice, useFormState, useQueryHistory } from '~/hooks';
import { makeSubmissionId } from '~/util';
import { ShareButton } from '~/components/results/share-button';
import type { HistoryEntry } from '~/hooks/use-query-history';

dayjs.extend(relativeTime);

interface HistoryEntryRowProps {
  entry: HistoryEntry;
}

const iconBtn = {
  as: 'a' as const,
  mx: 1,
  size: 'sm' as const,
  variant: 'ghost' as const,
  colorScheme: 'secondary' as const,
};

export const HistoryEntryRow = (props: HistoryEntryRowProps): JSX.Element => {
  const { entry } = props;
  const { web, messages } = useConfig();
  const toast = useToast();
  const getDevice = useDevice();

  const open = useQueryHistory(s => s.open);
  const remove = useQueryHistory(s => s.remove);
  const prefillForm = useFormState(s => s.prefillForm);
  const setStatus = useFormState(s => s.setStatus);
  const setSubmissionId = useFormState(s => s.setSubmissionId);

  const deviceIds = Object.keys(entry.results);
  const isSingleDevice = deviceIds.length === 1;
  const hasOutput = deviceIds.some(id => 'output' in entry.results[id]);

  const failStale = () =>
    toast({ title: messages.historyDeviceUnavailable, status: 'error', isClosable: true });

  const handleRerun = () => {
    const valid = prefillForm(entry.query, getDevice);
    if (valid.length === 0) return failStale();
    setSubmissionId(makeSubmissionId());
    setStatus('results');
  };

  const handleNewTarget = () => {
    const valid = prefillForm({ ...entry.query, queryTarget: [] }, getDevice);
    if (valid.length === 0) return failStale();
    setStatus('form');
  };

  return (
    <Flex
      px={3}
      py={2}
      w="100%"
      align="center"
      justify="space-between"
      borderTopWidth="1px"
      _first={{ borderTopWidth: 0 }}
    >
      <Flex direction="column" textAlign="left" minW={0} mr={2}>
        <Text fontSize="sm" fontWeight="medium" isTruncated>
          {entry.labels.locations.join(', ')} · {entry.labels.type} · {entry.labels.target}
        </Text>
        <Text fontSize="xs" color="gray.500">
          {dayjs(entry.savedAt).fromNow()}
        </Text>
      </Flex>
      <HStack spacing={0} flex="0 0 auto">
        {hasOutput && (
          <Tooltip hasArrow label={web.text.historyOpen} placement="top">
            <Button {...iconBtn} aria-label={web.text.historyOpen} onClick={() => open(entry.id)}>
              <DynamicIcon icon={{ fi: 'FiEye' }} boxSize="16px" />
            </Button>
          </Tooltip>
        )}
        {isSingleDevice && <ShareButton cacheId={entry.results[deviceIds[0]].id} />}
        <Tooltip hasArrow label={web.text.historyRerun} placement="top">
          <Button {...iconBtn} aria-label={web.text.historyRerun} onClick={handleRerun}>
            <DynamicIcon icon={{ fi: 'FiRepeat' }} boxSize="16px" />
          </Button>
        </Tooltip>
        <Tooltip hasArrow label={web.text.historyNewTarget} placement="top">
          <Button {...iconBtn} aria-label={web.text.historyNewTarget} onClick={handleNewTarget}>
            <DynamicIcon icon={{ fi: 'FiEdit' }} boxSize="16px" />
          </Button>
        </Tooltip>
        <Tooltip hasArrow label={web.text.historyDelete} placement="top">
          <Button
            {...iconBtn}
            aria-label={web.text.historyDelete}
            colorScheme="red"
            onClick={() => remove(entry.id)}
          >
            <DynamicIcon icon={{ fi: 'FiTrash2' }} boxSize="16px" />
          </Button>
        </Tooltip>
      </HStack>
    </Flex>
  );
};
```

Note: `web.text` is camelCased at runtime (`CamelCasedProperties<_Text>`), so the property names used above are `historyOpen`, `historyRerun`, `historyNewTarget`, `historyDelete`. The test asserts the rendered `aria-label` **values** ("Open", "Share", "Delete"), which are the defaults those fields carry — so the assertions hold regardless of the property names.

Add to `hyperglass/ui/components/history/index.ts`:

```ts
export * from './history-entry-row';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test components/history/history-entry-row.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/history/history-entry-row.tsx hyperglass/ui/components/history/index.ts hyperglass/ui/components/history/history-entry-row.test.tsx
git commit -m "feat(ui): add HistoryEntryRow with Open/Share/Re-run/New-target/Delete"
```

---

### Task 19: `RecentQueries` container

**Files:**
- Create: `hyperglass/ui/components/history/recent-queries.tsx`
- Modify: `hyperglass/ui/components/history/index.ts`
- Test: `hyperglass/ui/components/history/recent-queries.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `hyperglass/ui/components/history/recent-queries.test.tsx`:

```tsx
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TestWrapper } from '~/test/wrapper'; // adjust to actual shared helper
import { RecentQueries } from './recent-queries';
import { useQueryHistory } from '~/hooks';
import type { HistoryEntry } from '~/hooks/use-query-history';

// Force the "form is pristine" branch: mock useFormInteractive -> false.
vi.mock('~/hooks/use-form-state', async (orig) => {
  const actual = await orig<typeof import('~/hooks/use-form-state')>();
  return { ...actual, useFormInteractive: () => false };
});

const entry: HistoryEntry = {
  id: 's1',
  savedAt: Date.now(),
  query: { queryLocation: ['core1'], queryType: 'bgp_route', queryTarget: ['8.8.8.0/24'] },
  labels: { locations: ['Core 1'], type: 'BGP Route', target: '8.8.8.0/24' },
  results: { core1: {} as never },
};

beforeEach(() => {
  useQueryHistory.setState({ entries: [], openId: null });
});

describe('RecentQueries', () => {
  it('renders nothing when there are no entries', () => {
    const { container } = render(<TestWrapper><RecentQueries /></TestWrapper>);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the title and rows when entries exist', () => {
    useQueryHistory.setState({ entries: [entry], openId: null });
    render(<TestWrapper><RecentQueries /></TestWrapper>);
    expect(screen.getByText('Recent queries')).toBeInTheDocument();
    expect(screen.getByText(/Core 1 · BGP Route · 8.8.8.0\/24/)).toBeInTheDocument();
  });
});
```

(`TestWrapper`'s `useConfig` must supply `cache.historyEnabled = true`. The component gates on a mounted flag — render-after-mount — so the test, which runs an effect flush, will show content on the second tick; `@testing-library` `render` flushes effects, so the mounted state resolves to `true`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --dir ./hyperglass/ui test components/history/recent-queries.test.tsx`
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement**

Create `hyperglass/ui/components/history/recent-queries.tsx`:

```tsx
import {
  AlertDialog,
  AlertDialogBody,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  Box,
  Button,
  Flex,
  Text,
  useDisclosure,
} from '@chakra-ui/react';
import { useEffect, useRef, useState } from 'react';
import { useConfig } from '~/context';
import { useFormInteractive, useQueryHistory } from '~/hooks';
import { HistoryEntryRow } from './history-entry-row';

export const RecentQueries = (): JSX.Element | null => {
  const { cache, web } = useConfig();
  const formInteractive = useFormInteractive();
  const entries = useQueryHistory(s => s.entries);
  const clear = useQueryHistory(s => s.clear);

  // Render only after mount to avoid a next-export hydration mismatch
  // (server sees no localStorage; client rehydrates).
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const { isOpen, onOpen, onClose } = useDisclosure();
  const cancelRef = useRef<HTMLButtonElement>(null);

  if (!mounted || !cache.historyEnabled || formInteractive || entries.length === 0) {
    return null;
  }

  return (
    <Box w="100%" maxW={{ base: '100%', lg: '75%' }} mx="auto" my={4} textAlign="left">
      <Flex px={3} py={2} align="center" justify="space-between">
        <Text fontSize="sm" fontWeight="bold" textTransform="uppercase" color="gray.500">
          {web.text.historyTitle}
        </Text>
        <Button size="xs" variant="ghost" colorScheme="red" onClick={onOpen}>
          {web.text.historyClearAll}
        </Button>
      </Flex>
      <Box borderWidth="1px" rounded="lg" overflow="hidden">
        {entries.map(entry => (
          <HistoryEntryRow key={entry.id} entry={entry} />
        ))}
      </Box>

      <AlertDialog isOpen={isOpen} leastDestructiveRef={cancelRef} onClose={onClose}>
        <AlertDialogOverlay>
          <AlertDialogContent>
            <AlertDialogHeader>{web.text.historyClearConfirm}</AlertDialogHeader>
            <AlertDialogBody />
            <AlertDialogFooter>
              <Button ref={cancelRef} onClick={onClose}>
                {web.text.historyBack}
              </Button>
              <Button
                colorScheme="red"
                ml={3}
                onClick={() => {
                  clear();
                  onClose();
                }}
              >
                {web.text.historyClearAll}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialogOverlay>
      </AlertDialog>
    </Box>
  );
};
```

Add to `hyperglass/ui/components/history/index.ts`:

```ts
export * from './recent-queries';
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --dir ./hyperglass/ui test components/history/recent-queries.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hyperglass/ui/components/history/recent-queries.tsx hyperglass/ui/components/history/index.ts hyperglass/ui/components/history/recent-queries.test.tsx
git commit -m "feat(ui): add RecentQueries list container"
```

---

## Phase 8 — Integration

### Task 20: Render `RecentQueries` and the history-open view in `index.tsx`

**Files:**
- Modify: `hyperglass/ui/pages/index.tsx`
- Test: manual + existing suite (the view logic is exercised by component tests; index wiring is verified by typecheck + a smoke test below).

- [ ] **Step 1: Implement the view switch**

Replace `hyperglass/ui/pages/index.tsx` with:

```tsx
import dynamic from 'next/dynamic';
import { AnimatePresence } from 'framer-motion';
import { Box, Button, Flex } from '@chakra-ui/react';
import { If, Then, Else } from 'react-if';
import { Loading } from '~/elements';
import { useConfig } from '~/context';
import { useQueryHistory, useView } from '~/hooks';
import { SnapshotResults } from '~/components/results/snapshot-results';
import type { SnapshotResultsItem } from '~/components/results/snapshot-results';

import type { NextPage } from 'next';

const LookingGlassForm = dynamic<Dict>(
  () => import('~/components/looking-glass-form').then(i => i.LookingGlassForm),
  { loading: Loading },
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

  const openEntry = openId ? entries.find(e => e.id === openId) : undefined;

  if (openEntry) {
    const items: SnapshotResultsItem[] = Object.entries(openEntry.results).map(
      ([queryLocation, snapshot]) => ({ queryLocation, snapshot: snapshot as ResultSnapshot }),
    );
    return (
      <Box w="100%" maxW={{ base: '100%', md: '75%' }} mx="auto">
        <Flex justify="flex-start" mb={2}>
          <Button size="sm" variant="ghost" onClick={close}>
            {web.text.historyBack}
          </Button>
        </Flex>
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
```

- [ ] **Step 2: Typecheck + full UI test run**

Run: `pnpm --dir ./hyperglass/ui typecheck && pnpm --dir ./hyperglass/ui test`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add hyperglass/ui/pages/index.tsx
git commit -m "feat(ui): wire RecentQueries and history-open view into landing page"
```

---

### Task 21: Render the history hint in the form and result header

**Files:**
- Modify: `hyperglass/ui/components/looking-glass-form.tsx` (Query Type `labelAddOn`)
- Modify: `hyperglass/ui/components/results/individual.tsx` (result header `HStack`)

- [ ] **Step 1: Add the hint to the form**

In `hyperglass/ui/components/looking-glass-form.tsx`, the Query Type `FormField` already has a `labelAddOn` rendering `DirectiveInfoModal`. Render the hint next to it. Import:

```ts
import { HistoryDisabledHint } from '~/components/history';
```

Change the `labelAddOn` expression to include the hint (wrap both in a fragment):

```tsx
              labelAddOn={
                directive !== null && (
                  <>
                    <DirectiveInfoModal
                      name="queryType"
                      title={directive.name ?? null}
                      item={directive.info ?? null}
                      visible={selections.queryType !== null && directive.info !== null}
                    />
                    <HistoryDisabledHint directiveHistory={directive.history} />
                  </>
                )
              }
```

- [ ] **Step 2: Add the hint to the live result header**

In `hyperglass/ui/components/results/individual.tsx`, inside the header `HStack` (where `ShareButton`/`CopyButton`/`RequeryButton` render), add — only for live results (not snapshots):

```tsx
          {!snapshot && <HistoryDisabledHint directiveHistory={getDirective()?.history ?? true} />}
```

Add the import:

```ts
import { HistoryDisabledHint } from '~/components/history';
```

- [ ] **Step 3: Typecheck + tests**

Run: `pnpm --dir ./hyperglass/ui typecheck && pnpm --dir ./hyperglass/ui test components/looking-glass-form.test.tsx components/results/individual.test.tsx`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add hyperglass/ui/components/looking-glass-form.tsx hyperglass/ui/components/results/individual.tsx
git commit -m "feat(ui): show history-disabled hint in form and result header"
```

---

## Phase 9 — Verification & docs

### Task 22: Full lint, typecheck, and test sweep

- [ ] **Step 1: Backend**

Run: `pytest hyperglass --ignore hyperglass/plugins/external -q`
Expected: PASS (all new + existing tests).

- [ ] **Step 2: Backend lint**

Run: `task lint`
Expected: zero Ruff errors.

- [ ] **Step 3: Frontend**

Run: `pnpm --dir ./hyperglass/ui test && pnpm --dir ./hyperglass/ui typecheck`
Expected: PASS.

- [ ] **Step 4: Frontend lint/format**

Run: `task ui-lint`
Expected: zero Biome errors. If formatting differs, run `task ui-format` and re-commit.

- [ ] **Step 5: Commit any lint/format fixes**

```bash
git add -A
git commit -m "chore: lint/format pass for query-history" || echo "nothing to commit"
```

---

### Task 23: Manual verification (no automated coverage)

- [ ] Start hyperglass against a dev install with at least two devices that share a directive.
- [ ] Run a single-device query; return to the pristine form (click the title/reset); confirm the entry appears under "Recent queries" with a relative timestamp.
- [ ] Click **Open**; confirm the cached output renders and each result shows a Share button.
- [ ] Click **Share** on a single-device row; confirm a link is minted (or a graceful "expired" message after `cache.timeout`).
- [ ] Click **Re-run**; confirm a fresh query runs and a new (distinct) entry is added.
- [ ] Click **New target**; confirm the form is populated with the location/type and an empty target.
- [ ] **Delete** one entry and **Clear all**; reload the page and confirm persistence/clearing behavior.
- [ ] Run > `history_limit` distinct queries; confirm the oldest are evicted.
- [ ] Set a directive `history: false`, rebuild the UI; confirm its queries are never recorded and the hint shows by Query Type and in the result header.
- [ ] Set `cache.history_enabled: false`, rebuild the UI; confirm the list and the hint are both gone.

---

### Task 24: Docs and changelog

**Files:**
- Modify: operator configuration docs (the same doc that documents `cache.share_*` — find via `grep -rn "share_enabled" docs/`).
- Modify: `CHANGELOG` (Keep a Changelog format, mirror the share-results entry).

- [ ] **Step 1: Document the config**

Add documentation for `cache.history_enabled` (default true), `cache.history_limit` (default 10), and the per-directive `history` flag (default true). Note that, like all UI config, changing these requires a UI rebuild. Note the privacy caution: history stores query targets in the browser; disable or lower the limit on shared/public terminals.

- [ ] **Step 2: Changelog entry**

Add an "Added" entry: "Per-browser query history on the landing page (Open / Share / Re-run / Re-run with new target / Delete), with an operator kill-switch (`cache.history_enabled`), retention limit (`cache.history_limit`), and per-directive opt-out (`directives.<id>.history`)."

- [ ] **Step 3: Commit**

```bash
git add docs CHANGELOG*
git commit -m "docs: document query-history config and behavior"
```

---

## Self-Review Notes (for the implementer)

- **camelCase reminder:** backend `history_enabled` → UI `cache.historyEnabled`; `Text.history_open` → `web.text.historyOpen`; directive `history` stays `history`. All UI snippets in this plan already use the camelCased property names — match that when adding any further `web.text`/`cache`/`messages` access.
- **`TestWrapper`/`~/test/wrapper`** is a placeholder for whatever shared render helper the UI tests already use — inspect `hyperglass/ui/components/looking-glass-form.test.tsx` and reuse its provider setup (Chakra + `HyperglassProvider`/config). If none is shared, factor one out in Task 11 Step 1 and reuse it.
- **Recording-once invariant:** the effect deps `[dataUpdatedAt, submissionId]` capture both fresh and cache-served settles; `record()` is an idempotent upsert, so re-firing for the same `(submissionId, deviceId)` overwrites rather than duplicates.
- **Eviction layering:** `record()` slices to `limit`; `historyStorage` handles the rarer "still too big" quota case by stripping outputs then dropping entries.

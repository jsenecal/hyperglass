# Query History — Design

**Status:** Draft
**Date:** 2026-06-03
**Owner:** Jonathan Senecal

## Problem

A user who runs a query in hyperglass has no way to revisit it. The result lives only in the requesting browser's in-memory Zustand store (`useFormState.responses`) and is lost on reload or navigation. To re-run yesterday's `BGP Route` lookup, the user must re-enter location, type, and target by hand. There is no record of what was asked, no quick re-run, and no way to compare how a result evolved between runs.

We want a **per-browser query history** surfaced on the landing page: a list of recent successful queries the user can click to re-open the locally-cached output, share (if still cached server-side), re-run, or re-run against a different target.

This builds directly on the already-merged **share-results** feature (`/api/query/share/*`, the `ShareButton`, the read-only `Result` snapshot rendering, and `QueryResponse.id`).

## Goals

- Persist recent **successful** queries per browser (localStorage), surviving reloads and visits.
- Surface them on the landing page, below the form, on the clean (pristine) form view.
- Per entry, offer four actions plus delete: **Open** (locally-cached output), **Share** (single-device, reusing share-results), **Re-run**, **New target** (re-run with a different target), **Delete**.
- Keep a **timeline** of runs — repeated runs of the same query are distinct entries so a user can see how output evolved.
- Operator-configurable: a kill-switch and a retention count, flowing through the same build-time config path as `share_enabled`.
- No hard-coded user-visible strings (CLAUDE.md).
- Mobile-friendly and Lighthouse-100 accessible.

## Non-goals

- Server-side / cross-device history (history is per-browser localStorage only).
- Recording **failed** queries (timeouts, device errors). Only successful device results are stored.
- Cross-submission dedupe / collapsing identical queries (explicitly rejected — we keep each run as a timeline point).
- Any new backend storage or endpoints beyond two config fields. History is a frontend feature; it reuses the existing share endpoints for the Share action.
- Editing a stored query in place (other than the "New target" re-run affordance).
- Syncing the retention limit at runtime — like all UI config, it ships at build time and a change requires a UI rebuild.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Per-submission grouping.** One history entry = one Submit click, holding the form query plus every successful device result. Clicking Open replays the exact multi-device accordion. | Mirrors today's in-memory `responses` map and the existing `Result`/`Accordion` rendering. |
| 2 | **Successful results only.** Failed device results are never recorded. A fully-failed submission records nothing; a partially-failed one records the successful subset. | Matches share-results' "no failed queries" rule; Open always shows usable output. |
| 3 | **No dedupe — keep a timeline.** Each Submit (including Re-run from history) is a distinct entry with its own timestamp. | For a looking glass, watching how a route/ping evolves across runs is valuable; dedupe would destroy that signal. |
| 4 | **localStorage, on by default**, with an operator kill-switch (`history_enabled`), a configurable retention count (`history_limit`, default 10), a clear-all control, and a per-entry delete. | Convenient by default, operator-controlled on sensitive/public deployments, matching the `share_enabled` pattern. |
| 5 | **Count cap + FIFO + graceful output drop.** Keep newest N; on quota error drop oldest, then (if a single entry is still too big) store it without its output so Open falls back to Re-run. | Predictable footprint; never throws; full BGP tables can be large. |
| 6 | **Inline below the form, landing only.** The list shows on the pristine form view and unmounts once the form is interactive or results show. | Zero-click discoverability without cluttering the active query flow (chosen over a drawer / collapsed strip). |
| 7 | **Inline icon-button row per entry**, reusing the result-header idiom (ghost `Button` + `DynamicIcon` + `Tooltip`). | Visual consistency with the existing result controls. |
| 8 | **Row Share only for single-device entries.** Multi-device entries' Share icon Opens the entry, where each rendered `Result` carries its own per-device `ShareButton`. | A multi-device entry has one `cacheId` per device — a single row-level share is ambiguous. |
| 9 | **Zustand store + `persist` middleware** (Approach 1), not a bespoke hook or the existing form store. | Idiomatic here; `persist` handles serialization/versioning; keeps the ephemeral `useFormState` clean. |

## Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │ pages/index.tsx (view switch)                │
                        │   openId? → SnapshotResults (history-open)   │
                        │   else view==='results' → Results (live)     │
                        │   else → LookingGlassForm + RecentQueries    │
                        └───────────────┬─────────────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
┌───────▼────────┐            ┌─────────▼─────────┐           ┌─────────▼──────────┐
│ RecentQueries  │            │ Result (in        │           │ useQueryHistory    │
│  + EntryRow ×N │ actions →  │  Results view)    │ records → │  (zustand+persist) │
│  Open/Share/   │            │  effect on        │           │  entries[]         │
│  Re-run/New/Del│            │  dataUpdatedAt     │           │  record/remove/    │
└───────┬────────┘            └───────────────────┘           │  clear/open/close  │
        │ Open                                                 └─────────┬──────────┘
        │ prefillForm (Re-run/New target) → useFormState                 │ persist
        │ ShareButton (single-device) → /api/query/share/<cacheId>       ▼
        ▼                                                       localStorage
   SnapshotResults ← reused by pages/result/[id].tsx           "hyperglass.queryHistory"
```

History is entirely client-side. The only backend touch points are: (a) the existing share endpoints, used unchanged by the row Share action; and (b) two new config fields projected into the build-time `hyperglass.json`.

## Data model

localStorage key `hyperglass.queryHistory`, written through Zustand `persist` (`version: 1`, `migrate` stub, `partialize` → persist only `entries`).

```ts
// NEW shared interface. ShareResponse is refactored to `extends ResultSnapshot`.
interface ResultSnapshot {
  id: string;                       // backend cache id — used for share attempts
  output: QueryResponse['output'];
  format: QueryResponse['format'];
  level: ResponseLevel;
  timestamp: string;
  runtime: number;
  cached: boolean;
  keywords: string[];
  queryLabels: { location: string };
}

interface HistoryEntry {
  id: string;                       // local id == submissionId (crypto.randomUUID)
  savedAt: number;                  // epoch ms
  query: { queryLocation: string[]; queryType: string; queryTarget: string[] };
  labels: { locations: string[]; type: string; target: string }; // frozen display strings
  results: Record<string, ResultSnapshot>;   // keyed by device id; successful results only
}
```

- `query.queryLocation` and `labels.locations` reflect the **successful subset** (the keys of `results`). A partially-failed submission therefore re-runs only the devices that worked — the honest consequence of "successful only."
- `labels.*` are frozen at write time so a later device rename/removal does not break the row display or Open.

### Recording

Device results arrive asynchronously (each `Result` runs its own `useLGQuery`). Recording is triggered by a small effect in `Result`, keyed on `dataUpdatedAt` + `submissionId` — **not** React Query's `onSuccess`, which does not fire when a result is served from RQ's in-memory cache without a refetch (which would silently skip recording on some re-runs):

```ts
useEffect(() => {
  if (!historyEnabled || snapshot || readOnly) return;        // skip share/history-open renders
  if (data?.level === 'success' && submissionId) {
    recordHistory({ submissionId, deviceId, deviceLabel, query, labels, snapshot: toSnapshot(data), limit });
  }
}, [dataUpdatedAt, submissionId]);
```

`record()` is an **idempotent upsert** by `submissionId`: create the entry if absent (stamp `savedAt`), set `results[deviceId]`, merge the device label into `labels.locations`, add `deviceId` to `query.queryLocation`, and move the entry to the front. A force-refresh (same `submissionId`) just overwrites that run's snapshot. The existing in-memory `addResponse(device.id, data)` is left untouched.

`submissionId` is a fresh `crypto.randomUUID()` (with a tiny fallback for environments lacking it) generated **once per Submit** in `LookingGlassForm.submitHandler` and on Re-run, stored on `useFormState`.

### Retention & eviction

- Keep the newest **N** entries (`history_limit`, default 10).
- A custom `persist` `storage` (wrapping `createJSONStorage(() => localStorage)`):
  - slices to N on every write;
  - on `QuotaExceededError`, drops oldest entries one at a time and retries;
  - if a single entry alone still won't fit, stores it with `results` stripped (metadata only). Such an entry's row swaps **Open → Re-run** (tooltip notes the local copy was dropped).
  - all access is `try/catch`'d; if localStorage is unavailable (private mode), the feature degrades to in-memory for the session without crashing.

## Frontend changes

### Store — `hooks/use-query-history.ts`

```ts
interface QueryHistoryState {
  entries: HistoryEntry[];
  openId: string | null;            // UI-only, NOT persisted
  record(input: RecordInput): void; // upsert by submissionId, promote to front, apply limit
  remove(id: string): void;
  clear(): void;
  open(id: string): void;
  close(): void;
}
```

`record()` takes `limit` in its input (supplied by the calling hook from `useConfig()`), keeping the store config-agnostic. `useRecordHistory()` is a thin wrapper hook that reads `cache.historyEnabled` + `cache.historyLimit` and no-ops when disabled.

### `useFormState` extraction — `prefillForm`

`locationChange` currently bundles the directive-intersection computation (`filtered.types`) with react-hook-form error signaling. Extract the **pure state computation** into a reusable `prefillForm(query, getDevice)` store action (sets `form`, `selections`, `filtered`; no RHF). `locationChange` calls that core plus its error handling. History actions use `prefillForm` and need no FormProvider/RHF access — the Results view renders purely from store form values.

`prefillForm` filters locations through `getDevice`; if no valid devices remain (renamed/removed), Re-run/New-target abort and toast `messages.historyDeviceUnavailable`.

### Components

- **`components/history/recent-queries.tsx`** — list container. Renders only when `cache.historyEnabled` AND `entries.length > 0` AND `!useFormInteractive()` (pristine landing view), and only after `persist` rehydration (avoids `next export` hydration mismatch). Header: `historyTitle` label + a Clear-all button that confirms (Chakra `AlertDialog`/`Popover`) before `clear()`.
- **`components/history/history-entry-row.tsx`** — one row per entry, result-header button idiom. Left: location label(s) · type label · target · prominent relative timestamp (`dayjs().fromNow()`). Right icon row: **Open** (`FiEye`), **Share** (`FiShare2`, single-device only — renders the existing `ShareButton` with `cacheId`), **Re-run** (`FiRepeat`), **New target** (`FiEdit`), **Delete** (`FiTrash2`). Icon-only buttons carry `aria-label`s from config.

### View switch — `pages/index.tsx`

Add the in-place history-open mode:

```
if (openId && entry) → <SnapshotResults entries=[…] /> + Back (close())
else if view === 'results' → <Results />
else → <LookingGlassForm /> + <RecentQueries />
```

### Actions

- **Open** — `open(entry.id)`; renders `SnapshotResults` from `entry.results`; no backend call. Back → `close()`.
- **Re-run** — `prefillForm(entry.query, getDevice)` → set `queryTarget` → new `submissionId` → `setStatus('results')`. Concrete stored target skips the FQDN resolve modal.
- **New target** — `prefillForm({ ...entry.query, queryTarget: [] }, getDevice)`, keep `status: 'form'`; the populated form appears with an empty Target field (best-effort focus once it slides in).
- **Share** (single-device) — inline `<ShareButton cacheId={theSingleResult.id} />`; reuses its popover, copy, `410 → shareCreateExpired`, and `cache.shareEnabled` gate.
- **Delete** — `remove(entry.id)`.

### `Result` / `SnapshotResults` refactor

- Extract **`SnapshotResults`** (`components/results/snapshot-results.tsx`) from the inline `AnimatedDiv + Accordion` markup in `pages/result/[id].tsx`. Takes `Array<{ queryLocation: string; snapshot: ResultSnapshot }>`, renders one `<Result>` each. Reused by the share page (single) and history-open (1..N).
- `Result.snapshot` prop type: `ShareResponse` → `ResultSnapshot` (`ShareResponse extends ResultSnapshot`; every field the component reads is already in `ResultSnapshot`).
- Decouple the overloaded `readOnly`: add `showShare?: boolean` (default `!readOnly`). Share render → `{showShare && data?.id && <ShareButton/>}`; Requery stays `{!readOnly && …}`. History-open passes `readOnly` (no Requery) **+ `showShare`** (per-device Share visible) — enabling multi-device sharing after Open. `pages/result/[id].tsx` keeps `readOnly` (Share stays hidden there, unchanged behavior).

### TypeScript types — `types/config.d.ts`, `types/globals.d.ts`

- `config.d.ts`: add `historyEnabled: boolean`, `historyLimit: number` under `cache`; add the new `web.text` history strings; add `messages.historyDeviceUnavailable`.
- `globals.d.ts` (or wherever response types live): add `ResultSnapshot`; make `ShareResponse extends ResultSnapshot`.

### i18n — no hard-coded strings

New `web.text` fields (defaults in the backend `Text` model, projected to the frontend, added to the UI `Text` type — same path share-results used): `historyTitle`, `historyClearAll`, `historyClearConfirm`, `historyBack`, `historyOpen`, `historyShare`, `historyRerun`, `historyNewTarget`, `historyDelete`. New `messages.historyDeviceUnavailable` (error-shaped). Relative time via `dayjs().fromNow()` — no literal copy.

## Backend changes

### `hyperglass/models/config/cache.py`

```python
class Cache(HyperglassModel):
    timeout: int = 600
    show_text: bool = True
    share_enabled: bool = True
    share_timeout: int = 604800
    share_sliding: bool = False
    refresh_min_interval: int = 120
    history_enabled: bool = True      # NEW — UI kill switch
    history_limit: int = 10           # NEW — UI retention count
```

### `Params.frontend()` — `hyperglass/models/config/params.py`

Extend the `cache` include set so the two new fields ship in build-time `hyperglass.json`:

```python
"cache": {"show_text", "timeout", "share_enabled", "share_timeout",
          "refresh_min_interval", "history_enabled", "history_limit"},
```

`/api/info` and `APIParams` are untouched. Like all UI config, flipping these requires a UI rebuild — documented alongside the feature.

### Backend `Text` model

Add the new history string fields (with defaults) to the `Text` model and ensure they project to the frontend `web.text`, mirroring how share-results added its strings.

## Edge cases

| Case | Behavior |
|------|----------|
| `history_enabled = false` | Recording no-ops; `RecentQueries` hidden. Existing localStorage entries remain but are never shown. |
| Output too big to store | Entry kept without `output`; row swaps Open → Re-run (tooltip explains). |
| Device renamed/removed | Open still works (frozen snapshot/labels). Re-run / New-target hit the stale-device guard → toast `historyDeviceUnavailable`. |
| `cacheId` aged out of Redis | Share returns 410 → existing `shareCreateExpired` message. |
| Multi-device partial success | Entry holds the successful subset only. |
| Fully-failed submission | No entry recorded. |
| localStorage unavailable (private mode) | Storage adapter try/catches; in-memory for the session, no crash. |
| `next export` hydration | `RecentQueries` renders only after `persist` rehydrates → no SSR mismatch. |
| No `crypto.randomUUID` | Tiny fallback id generator. |
| Force-refresh in the live Results view | Same `submissionId` → upsert overwrites that run's snapshot (not a new entry). |
| Re-run from history | New Submit → new `submissionId` → new timeline entry. |

## Testing

### Frontend (Vitest, `hyperglass/ui/`)

- **Store** (mocked localStorage): upsert + group by `submissionId`; promote-to-front; N-cap eviction; quota → drop-oldest then strip-output; `remove`; `clear`; persist round-trip; `crypto.randomUUID` fallback.
- **`RecentQueries`**: hidden when disabled / empty / form-interactive; renders rows; clear-all confirm flow; renders only after rehydration.
- **`HistoryEntryRow`**: Share icon only on single-device entries; Open → `open()`; Delete → `remove()`; Re-run sets store + status + new `submissionId`; New-target sets store + empty target; stale-device guard toasts; output-stripped entry swaps Open → Re-run.
- **`Result`**: `showShare` defaults to `!readOnly`; history mode (readOnly + showShare) shows Share, hides Requery; snapshot renders.
- **`SnapshotResults`**: renders N results for a multi-device entry.

### Backend (pytest, `hyperglass/`)

- `Cache` defaults: `history_enabled is True`, `history_limit == 10`.
- `Params.frontend()` projects `history_enabled` / `history_limit` into the cache include set (and they appear in the serialized output).
- `Text` model exposes the new history string defaults and they project to the frontend.

### Manual

- Run a query; confirm it appears in Recent queries on returning to the pristine form.
- Multi-device query: Open replays all device results; each shows its own Share button.
- Single-device query: row Share mints a link (or 410s gracefully after `cache.timeout`).
- Re-run and New-target prefill correctly, including multi-device.
- Delete and Clear-all behave; survive reload; respect `history_limit`; `history_enabled=false` hides the list after a rebuild.

## Risks

- **localStorage footprint.** Capped by `history_limit` and graceful eviction, but large structured outputs (full BGP tables) consume the per-origin quota quickly. Operators on shared kiosks may lower `history_limit` or disable the feature.
- **Privacy on shared machines.** History persists query targets in the browser for the next user. Mitigated by the operator kill-switch, clear-all, and per-entry delete; documented in operator docs (the same caution share-results raised about sensitive output).
- **Coupling to share-results internals.** The refactor touches `Result` and extracts `SnapshotResults` from `pages/result/[id].tsx`. A future change to either must keep the share page and history-open in sync (mitigated by `SnapshotResults` being the single rendering source).
- **Recording-trigger correctness.** Relying on a `dataUpdatedAt`-keyed effect rather than `onSuccess` is deliberate (cache-served results). Tests must cover both fresh-fetch and cache-served paths to prevent silent non-recording regressions.

## Deferred

- Server-side / cross-device history.
- Recording failed queries (for "retry what just failed").
- A dedicated full-page history view or a results-view-reachable drawer (chosen against landing-only inline placement for v1).
- Pinning / naming / annotating entries.
- Exporting history.

# Share / result / form-prefill flow — design

Date: 2026-06-09
Status: Approved (pending spec review)
Scope: hyperglass UI (`hyperglass/ui/`) only. No backend changes.

## Problem

Four user-reported defects in the result-viewing / sharing / history flow:

1. **"Run with a new target" (history) doesn't populate the form.** Location
   appears selected but is inert, Query Type is blank, Target is blank.
2. **Inconsistent back controls.** Live query results use a green bottom-left
   arrow (`ResetButton`, `FaAngleLeft`); the opened-history "view result" uses a
   plain text "Back" button; the shared `/result/<id>` page has no back control
   (but does show a "Snapshot taken at…/Expires…" banner the user wants kept).
3. **URL does not reflect the result being viewed.** Opening a stored result
   leaves the address bar unchanged, so it is not linkable / back-navigable.
4. **Shared results lack re-run actions, and "Run a fresh query" is broken** —
   it navigates to `/?…` but the form does not populate.

## Root causes

The form has **three** representations of its state that must stay in sync:

- **react-hook-form (RHF) values** — drive validation and gate submit (the vest
  resolver validates RHF values; `handleSubmit` won't call `submitHandler` if
  RHF says the form is invalid).
- **Zustand `form`** — drives `submitHandler`, `useView`, the gallery
  `LocationCard` `defaultChecked`, and directive filtering.
- **Zustand `selections`** — drive the *displayed* value of the Location and
  Query Type dropdowns (`<Select value={selections.queryType} />`).

The two prefill paths each sync a different subset:

- `prefillForm` (`hooks/use-form-state.ts`, used by history Re-run / New-target)
  sets Zustand `form` + `selections.queryLocation`, but hardcodes
  `selections.queryType: null` and **never touches RHF**. Result: Query Type
  shows blank, and a prefilled "New target" form cannot be submitted because RHF
  still believes `queryLocation` is empty.
- The URL-param effect (`looking-glass-form.tsx`, used by "Run a fresh query")
  sets RHF + Zustand `form` but **also never sets `selections.queryType`**.

So both items 1 and 4 share a root cause: prefill never populates
`selections.queryType`, and the two paths sync different subsets of the three
state representations (they have drifted twice now).

For item 2, the green back control is `components/reset-button.tsx`, hardwired
to `status === 'results'` and `resetForm`. For item 4's missing actions,
`components/results/individual.tsx` hides `RequeryButton`/`ShareButton` whenever
`readOnly` (the share and snapshot views).

## Approved product decisions

- **Item 3 — URL on results:** *Only for opened results.* Live query results
  keep the bare URL (`/`). Opening a stored result reflects in the URL:
  `/result/<id>` when a share id is known, otherwise a deep-link
  `/?location=…&target=…&type=…`. The shared view stays `/result/<id>`.
- **Item 2 — back control:** Use the green bottom-left arrow on **both** the
  opened-history view and the shared `/result/<id>` page, replacing the plain
  text "Back". Keep the snapshot/expires banner on the shared page.
- **Item 4 — shared re-run:** Re-running from a shared result navigates to the
  looking glass home, populates the form, and **auto-runs** a fresh live query.

## Design

Chosen approach for prefill (vs. patching each path separately): **one prefill
entry point + a Zustand→RHF mirror.** This collapses the duplication that caused
the drift.

### Phase 1 — prefill correctness (fixes item 1 + populate-half of item 4)

- `prefillForm(query, getDevice)` becomes the single source of truth. In
  addition to today's behavior it sets `selections.queryType` by finding the
  directive in the computed `filtered.types` whose `id === query.queryType` and
  building `{ value: id, label: name }` (or `null` when the type is empty/
  unknown, e.g. New-target which clears only the target).
- Add an effect in `looking-glass-form.tsx` that mirrors Zustand `form` into RHF
  (`setValue`) whenever they diverge, guarded against update loops. This makes a
  prefilled form (including history "New target") actually submittable.
- Rewrite the URL-param prefill effect to call `prefillForm` (passing
  `getDevice`) instead of duplicating the location/type/target wiring. The
  mirror effect then pushes values into RHF.
- Make the gallery `LocationCard` reflect the prefilled selection via a
  controlled checked state derived from `form.queryLocation`, not a one-shot
  `defaultChecked`, so cards-mode prefill is visible and active.

### Phase 2 — consistent back control + shared actions

- Generalize `ResetButton` into a reusable floating back control
  (`FloatingBackButton`) with props `{ isVisible, onClick, label }`, and migrate
  the single live-results call site to it (no compatibility wrapper).
  - Live results → resets the form (unchanged behavior).
  - Opened-history view (`pages/index.tsx`) → green arrow, `onClick = close()`;
    remove the text `historyBack` button.
  - Shared `/result/[id]` → green arrow returning to `/`; keep the banner.
- In `individual.tsx`, replace the blanket `readOnly` action-hiding with
  snapshot-aware actions: add **Re-run** (`FiRepeat`) and **New target**
  (`FiEdit`) to snapshot results (shared page + opened history), mirroring the
  history row. They build the deep-link and navigate to `/`; Re-run includes an
  auto-run flag. Remove the broken "Run a fresh query" text link from
  `pages/result/[id].tsx` in favor of these icons.

### Phase 3 — URL reflects opened results (item 3)

- Add `shareId?: string` to `HistoryEntry` (`hooks/use-query-history.ts`).
  Persist it when a user shares from within an opened entry (capture the id
  minted by `ShareButton` / `useShareCreate`).
- `open(id)` updates the address bar. When the entry has a `shareId`, navigate
  to `/result/<shareId>` (a normal client navigation to the canonical share
  page — not shallow, since it's a different route). Otherwise stay on the index
  page and shallow-push the deep-link `/?location=…&target=…&type=…` so the
  opened-entry view remains mounted and is bookmarkable. `close()` shallow-pushes
  back to `/`. (Only the deep-link case is shallow; the `/result/<id>` case is a
  real route change handled by the share page.)
- Exclude `openId` from the history `persist` partialize so reloading `/` shows
  the form rather than a stale opened entry.
- This phase is the most intricate (shallow routing + browser-back interplay)
  and is kept isolated so it cannot destabilize Phases 1–2.

### Auto-run mechanism (shared/deep-link)

The deep-link prefill already keys off URL query params. Add an opt-in `run`
flag (e.g. `?…&run=1`) that, after a successful prefill where the form is valid,
stamps a `submissionId` and sets status to `results` (the same path
`submitHandler` takes for a non-FQDN query). Without the flag, prefill only
populates (used by New-target). The flag is consumed once (the existing
`prefillApplied` ref guard prevents re-runs on re-render).

## Components and boundaries

- `hooks/use-form-state.ts` — `prefillForm` owns full form/selection/filtered/
  target population. Pure state transition; testable in isolation.
- `components/looking-glass-form.tsx` — owns RHF mirroring and URL→prefill +
  optional auto-run. Thin orchestration over `prefillForm`.
- `components/<floating-back-button>` — presentational; `{ isVisible, onClick,
  label }`. No knowledge of form/history/share.
- `components/results/individual.tsx` — snapshot-aware action row.
- `hooks/use-query-history.ts` — `shareId` field + open/close URL side-effects.

## Testing

- **Unit (Vitest):**
  - `prefillForm` populates `selections.queryType` from a matching directive and
    leaves it `null` for empty/unknown types.
  - The RHF mirror makes a prefilled form pass validation / be submittable.
  - History Re-run and New-target populate Location + Type (and Target for
    Re-run; cleared for New-target).
  - Shared-page Re-run/New-target render and build the correct deep-link, with
    Re-run carrying the auto-run flag.
  - Floating back control: visible per state, fires the right callback.
- **End-to-end headless-browser check** (the Playwright harness used for the
  share-download fix): build the export, load `/result/<id>`, click Re-run →
  assert it lands on `/`, the form is populated, and the query auto-runs;
  assert the green back arrow returns to `/`. Completion is gated on this real
  pass, not unit tests alone.

## Out of scope

- Backend changes (the share API and `/result/<id>` handler are unchanged).
- Auto-minting shares for live results (explicitly rejected in item 3).
- Any unrelated refactor of the results group or query hooks.

## Implementation order

Phase 1 → Phase 2 → Phase 3. Each phase ends green (lint + unit). The end-to-end
browser check runs after Phase 2 (covers items 1, 2, 4) and again after Phase 3.

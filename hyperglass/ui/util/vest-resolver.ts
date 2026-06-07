import type { FieldErrors, FieldValues, Resolver } from 'react-hook-form';
import type { SuiteResult } from 'vest';

/**
 * Structural subset of a vest suite — only what the resolver calls. Typing
 * against vest's full `Suite` generics couples this to the suite callback's
 * exact signature (e.g. optional `data` params break inference).
 */
interface RunnableSuite<T> {
  runStatic(data: T): SuiteResult<string, string>;
}

/**
 * Bridge a vest suite into a react-hook-form resolver.
 *
 * Replaces `vestResolver` from `@hookform/resolvers/vest`. Every released
 * version of @hookform/resolvers (≤5.4.0 as of 2026-06) statically imports
 * the `vest/promisify` subpath, which vest removed in v6.0.0 — so bundling
 * or testing with vest 6 fails module resolution outright, and no upstream
 * fix or tracking issue exists. Since that resolver was this app's only use
 * of @hookform/resolvers, it was replaced with this implementation and the
 * dependency removed.
 *
 * Why not @hookform/resolvers' `standardSchemaResolver` with vest 6's
 * Standard Schema support (`suite['~standard']`): vest's Standard Schema
 * adapter snapshots the result synchronously, so a suite containing async
 * tests reports no issues while still pending — invalid data would pass
 * validation silently. `runStatic()` returns a thenable that settles after
 * async tests finish (vest 6's replacement for `promisify`/`done()`), and is
 * stateless, which is exactly the contract a resolver wants.
 *
 * Scope: exactly what the looking-glass form needs — flat field names and
 * the first error message per failing field. The upstream resolver
 * additionally nests dotted field paths (`toNestErrors`), populates
 * `FieldError.types` under `criteriaMode: 'all'`, and supports
 * `shouldUseNativeValidation`; none of those are used here.
 */
export function vestResolver<T extends FieldValues>(suite: RunnableSuite<T>): Resolver<T> {
  return async values => {
    const result = await suite.runStatic(values);

    if (!result.hasErrors()) {
      return { values, errors: {} };
    }

    const errors: Record<string, { type: string; message: string }> = {};
    for (const [field, messages] of Object.entries(result.getErrors())) {
      if (messages.length > 0) {
        errors[field] = { type: 'validation', message: messages[0] };
      }
    }
    return { values: {}, errors: errors as FieldErrors<T> };
  };
}

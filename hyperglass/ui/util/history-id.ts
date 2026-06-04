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

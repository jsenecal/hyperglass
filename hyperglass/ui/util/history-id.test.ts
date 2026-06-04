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

import { describe, expect, it } from 'vitest';
import { create, enforce, test as vestTest } from 'vest';
import { vestResolver } from './vest-resolver';

import type { ResolverOptions } from 'react-hook-form';

interface Data {
  queryTarget: string[];
  queryType: string;
}

// Vest suites are stateful (results persist between runs), so each test gets
// a fresh suite instance.
const makeSuite = () =>
  create((data: Data) => {
    vestTest('queryTarget', 'Query Target is required.', () => {
      enforce(data.queryTarget).isArrayOf(enforce.isString()).isNotEmpty();
    });
    vestTest('queryType', 'Query Type is required.', () => {
      enforce(data.queryType).isNotEmpty();
    });
  });

const options = {} as ResolverOptions<Data>;

describe('vestResolver - bridge vest suites to react-hook-form', () => {
  it('returns values and no errors for valid data', async () => {
    const resolver = vestResolver<Data>(makeSuite());
    const values: Data = { queryTarget: ['192.0.2.0/24'], queryType: 'bgp_route' };
    const result = await resolver(values, undefined, options);
    expect(result.errors).toEqual({});
    expect(result.values).toEqual(values);
  });

  it('returns the first error message per failing field and empty values', async () => {
    const resolver = vestResolver<Data>(makeSuite());
    const result = await resolver({ queryTarget: [], queryType: '' }, undefined, options);
    expect(result.values).toEqual({});
    expect(result.errors.queryTarget?.message).toBe('Query Target is required.');
    expect(result.errors.queryType?.message).toBe('Query Type is required.');
  });

  it('only reports errors for failing fields', async () => {
    const resolver = vestResolver<Data>(makeSuite());
    const result = await resolver(
      { queryTarget: ['192.0.2.0/24'], queryType: '' },
      undefined,
      options,
    );
    expect(result.errors.queryTarget).toBeUndefined();
    expect(result.errors.queryType?.message).toBe('Query Type is required.');
  });

  it('waits for async tests via the suite result done() callback', async () => {
    const suite = create((data: Data) => {
      vestTest('queryTarget', 'Async validation failed.', async () => {
        await new Promise(resolve => setTimeout(resolve, 10));
        enforce(data.queryTarget).isNotEmpty();
      });
    });
    const resolver = vestResolver<Data>(suite);
    const result = await resolver({ queryTarget: [], queryType: '' }, undefined, options);
    expect(result.errors.queryTarget?.message).toBe('Async validation failed.');
  });
});

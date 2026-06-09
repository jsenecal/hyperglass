import '@testing-library/jest-dom';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useFormInteractive, useFormState, useView } from './use-form-state';

// Exercises the useShallow-wrapped object selectors in useView and
// useFormInteractive. With zustand v5, an unmemoized object-returning
// selector throws "Maximum update depth exceeded" at render time, so these
// renders double as a regression guard for that failure mode.

beforeEach(async () => {
  await act(() => useFormState.getState().reset());
});

describe('useView', () => {
  it('returns form when the form is empty', () => {
    const { result } = renderHook(() => useView());
    expect(result.current).toBe('form');
  });

  it('returns results when status is results and the form is populated', () => {
    const { result } = renderHook(() => useView());
    act(() => {
      const { setFormValue, setStatus } = useFormState.getState();
      setFormValue('queryLocation', ['test1']);
      setFormValue('queryType', 'juniper_bgp_route');
      setFormValue('queryTarget', ['192.0.2.0/24']);
      setStatus('results');
    });
    expect(result.current).toBe('results');
  });

  it('returns form when status is results but the form is incomplete', () => {
    const { result } = renderHook(() => useView());
    act(() => {
      const { setFormValue, setStatus } = useFormState.getState();
      setFormValue('queryLocation', ['test1']);
      setStatus('results');
    });
    expect(result.current).toBe('form');
  });
});

describe('useFormInteractive', () => {
  it('is false for an untouched form', () => {
    const { result } = renderHook(() => useFormInteractive());
    expect(result.current).toBe(false);
  });

  it('is true once a location is selected', () => {
    const { result } = renderHook(() => useFormInteractive());
    act(() => {
      useFormState
        .getState()
        .setSelection('queryLocation', [{ value: 'test1', label: 'Test Router 1' }]);
    });
    expect(result.current).toBe(true);
  });

  it('is true when status is results', () => {
    const { result } = renderHook(() => useFormInteractive());
    act(() => {
      useFormState.getState().setStatus('results');
    });
    expect(result.current).toBe(true);
  });
});

describe('useFormState.submissionId', () => {
  beforeEach(async () => {
    await useFormState.getState().reset();
  });

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

describe('useFormState.prefillForm', () => {
  beforeEach(async () => {
    await useFormState.getState().reset();
  });

  const device = (id: string) =>
    ({
      id,
      name: id.toUpperCase(),
      directives: [{ id: 'bgp_route', name: 'BGP Route', groups: ['ip'] }],
    }) as never;

  it('sets form values and selections for valid locations', () => {
    const getDevice = (id: string) => (id === 'core1' ? device('core1') : null);
    useFormState
      .getState()
      .prefillForm(
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
    const valid = useFormState
      .getState()
      .prefillForm(
        { queryLocation: ['core1', 'ghost'], queryType: 'bgp_route', queryTarget: ['x'] },
        getDevice as never,
      );
    expect(valid).toEqual(['core1']);
    expect(useFormState.getState().form.queryLocation).toEqual(['core1']);
  });
});

describe('useFormState.prefillForm selections.queryType', () => {
  const testDevice = {
    id: 'test1',
    name: 'Test Router 1',
    directives: [{ id: 'juniper_bgp_route', name: 'BGP Route', groups: [] }],
  } as never;
  const getDevice = (id: string) => (id === 'test1' ? testDevice : null);

  it('sets the query-type selection from the matching directive', () => {
    useFormState.getState().prefillForm(
      { queryLocation: ['test1'], queryType: 'juniper_bgp_route', queryTarget: ['192.0.2.0/24'] },
      getDevice as never,
    );
    const { selections, form } = useFormState.getState();
    expect(form.queryType).toBe('juniper_bgp_route');
    expect(selections.queryType).toEqual({ value: 'juniper_bgp_route', label: 'BGP Route' });
  });

  it('leaves the query-type selection null for an empty type', () => {
    useFormState.getState().prefillForm(
      { queryLocation: ['test1'], queryType: '', queryTarget: [] },
      getDevice as never,
    );
    expect(useFormState.getState().selections.queryType).toBeNull();
  });
});

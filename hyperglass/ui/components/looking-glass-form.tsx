import { Flex, ScaleFade, SlideFade, chakra } from '@chakra-ui/react';
import { vestResolver } from '@hookform/resolvers/vest';
import { useRouter } from 'next/router';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import vest, { test, enforce } from 'vest';
import { useShallow } from 'zustand/react/shallow';
import {
  DirectiveInfoModal,
  FormField,
  QueryLocation,
  QueryTarget,
  QueryType,
  SubmitButton,
} from '~/components';
import { useConfig } from '~/context';
import { FormRow } from '~/elements';
import { useDevice, useFormState, useGreeting, useStrf } from '~/hooks';
import { Directive, isQueryField, isString } from '~/types';
import { isFQDN } from '~/util';

import type { FormData, OnChangeArgs } from '~/types';

export const LookingGlassForm = (): JSX.Element => {
  const { web, messages } = useConfig();
  const router = useRouter();

  const greetingReady = useGreeting(s => s.greetingReady);

  const getDevice = useDevice();
  const strF = useStrf();
  const setLoading = useFormState(s => s.setLoading);
  const setStatus = useFormState(s => s.setStatus);
  const locationChange = useFormState(s => s.locationChange);
  const setSelection = useFormState(s => s.setSelection);
  const setTarget = useFormState(s => s.setTarget);
  const setFormValue = useFormState(s => s.setFormValue);
  const { form, filtered, selections } = useFormState(
    useShallow(({ form, filtered, selections }) => ({ form, filtered, selections })),
  );

  const getDirective = useFormState(useCallback(s => s.getDirective, []));
  const resolvedOpen = useFormState(useCallback(s => s.resolvedOpen, []));
  const resetForm = useFormState(useCallback(s => s.reset, []));

  const noQueryType = strF(messages.noInput, { field: web.text.queryType });
  const noQueryLoc = strF(messages.noInput, { field: web.text.queryLocation });
  const noQueryTarget = strF(messages.noInput, { field: web.text.queryTarget });

  const queryTypes = useMemo(() => filtered.types.map(t => t.id), [filtered.types]);

  const formSchema = vest.create((data: FormData = {} as FormData) => {
    test('queryLocation', noQueryLoc, () => {
      enforce(data.queryLocation).isArrayOf(enforce.isString()).isNotEmpty();
    });
    test('queryTarget', noQueryTarget, () => {
      enforce(data.queryTarget).isArrayOf(enforce.isString()).isNotEmpty();
    });
    test('queryType', noQueryType, () => {
      enforce(data.queryType).inside(queryTypes);
    });
  });

  const formInstance = useForm<FormData>({
    resolver: vestResolver(formSchema),
    defaultValues: {
      queryTarget: [],
      queryLocation: [],
      queryType: '',
    },
  });

  const { handleSubmit, register, setValue, setError, clearErrors } = formInstance;

  const isFqdnQuery = useCallback(
    (target: string | string[], fieldType: Directive['fieldType'] | null): boolean =>
      (typeof target === 'string' || Array.isArray(target)) &&
      fieldType === 'text' &&
      isFQDN(target),
    [],
  );

  const directive = useMemo<Directive | null>(() => {
    const tmp = getDirective();
    if (tmp !== null && tmp.fieldType === null) {
      setFormValue('queryTarget', ['null']);
      setValue('queryTarget', ['null']);
    }
    return tmp;
  }, [form.queryType, form.queryLocation, getDirective]);

  function submitHandler(): void {
    if (process.env.NODE_ENV === 'development') {
      console.table({
        'Query Location': form.queryLocation.toString(),
        'Query Type': form.queryType,
        'Query Target': form.queryTarget,
        'Selected Directive': directive?.name ?? null,
      });
    }

    // Before submitting a query, make sure the greeting is acknowledged if required. This should
    // be handled before loading the app, but people be sneaky.
    if (!greetingReady) {
      resetForm();
      location.reload();
      return;
    }

    // Determine if queryTarget is an FQDN.
    const isFqdn = isFqdnQuery(form.queryTarget, directive?.fieldType ?? null);

    if (greetingReady && !isFqdn) {
      setStatus('results');
      return;
    }

    if (greetingReady && isFqdn) {
      setLoading(true);
      resolvedOpen();
      return;
    }
    console.group('%cSomething went wrong', 'color:red;');
    console.table({
      'Greeting Required': web.greeting.required,
      'Greeting Ready': greetingReady,
      'Query Target': form.queryTarget,
      'Query Type': form.queryType,
      'Is FQDN': isFqdn,
    });
    console.groupEnd();
  }

  const handleLocChange = (locations: string[]) =>
    locationChange(locations, { setError, clearErrors, getDevice, text: web.text });

  // Pre-fill form from URL query params (?location=&target=&type=).
  // Applied once on mount when router.isReady — a ref guard prevents re-applying
  // if the component re-renders after the user has edited the form.
  const prefillApplied = useRef(false);
  useEffect(() => {
    if (!router.isReady || prefillApplied.current) return;
    prefillApplied.current = true;

    const { location, target, type } = router.query;

    if (typeof location === 'string') {
      setValue('queryLocation', [location]);
      // Drive Zustand state through locationChange so filtered.types is populated.
      locationChange([location], { setError, clearErrors, getDevice, text: web.text });
      // Also populate selections.queryLocation so the dropdown <Select value=...> and
      // the gallery <LocationCard defaultChecked=...> both reflect the pre-filled value.
      // Guard for unknown location IDs: skip selection rather than inserting a null/bad option.
      const device = getDevice(location);
      if (device !== null) {
        setSelection('queryLocation', [{ value: device.id, label: device.name }]);
      }
    }
    if (typeof type === 'string') {
      setValue('queryType', type);
      setFormValue('queryType', type);
    }
    if (typeof target === 'string') {
      setValue('queryTarget', [target]);
      setFormValue('queryTarget', [target]);
      setTarget({ display: target });
    }
  }, [router.isReady, router.query]);

  function handleChange(e: OnChangeArgs): void {
    // Signal the field & value to react-hook-form.
    if (isQueryField(e.field)) {
      setValue(e.field, e.value);
    } else {
      throw new Error(`Field '${e.field}' is not a valid form field.`);
    }

    if (e.field === 'queryLocation' && Array.isArray(e.value)) {
      handleLocChange(e.value);
    } else if (e.field === 'queryType' && isString(e.value)) {
      setValue('queryType', e.value);
      setFormValue('queryType', e.value);
      if (form.queryTarget.length !== 0) {
        // Reset queryTarget as well, so that, for example, selecting BGP Community, and selecting
        // a community, then changing the queryType to BGP Route doesn't preserve the selected
        // community as the queryTarget.
        setFormValue('queryTarget', []);
        setTarget({ display: '' });
      }
    } else if (e.field === 'queryTarget') {
      if (isString(e.value)) {
        setFormValue('queryTarget', [e.value]);
        setValue('queryTarget', [e.value]);
      }
      if (Array.isArray(e.value)) {
        setFormValue('queryTarget', e.value);
        setValue('queryTarget', e.value);
      }
    }
  }

  useEffect(() => {
    register('queryLocation', { required: true });
    register('queryType', { required: true });
  }, [register]);

  return (
    <FormProvider {...formInstance}>
      <chakra.form
        p={0}
        my={4}
        w="100%"
        mx="auto"
        textAlign="left"
        maxW={{ base: '100%', lg: '75%' }}
        onSubmit={handleSubmit(submitHandler)}
      >
        <FormRow>
          <FormField name="queryLocation" label={web.text.queryLocation}>
            <QueryLocation onChange={handleChange} label={web.text.queryLocation} />
          </FormField>
        </FormRow>
        <FormRow>
          <SlideFade offsetX={-100} in={filtered.types.length > 0} unmountOnExit>
            <FormField
              name="queryType"
              label={web.text.queryType}
              labelAddOn={
                directive !== null && (
                  <DirectiveInfoModal
                    name="queryType"
                    title={directive.name ?? null}
                    item={directive.info ?? null}
                    visible={selections.queryType !== null && directive.info !== null}
                  />
                )
              }
            >
              <QueryType onChange={handleChange} label={web.text.queryType} />
            </FormField>
          </SlideFade>
          <SlideFade
            offsetX={100}
            in={directive !== null && directive.fieldType !== null}
            unmountOnExit
          >
            {directive !== null && (
              <FormField name="queryTarget" label={web.text.queryTarget}>
                <QueryTarget
                  name="queryTarget"
                  register={register}
                  onChange={handleChange}
                  placeholder={directive.description}
                />
              </FormField>
            )}
          </SlideFade>
        </FormRow>
        <FormRow mt={0} justifyContent="flex-end">
          <Flex
            my={2}
            w="100%"
            ml="auto"
            maxW="100%"
            flex="0 0 0"
            flexDir="column"
            mr={{ base: 0, lg: 2 }}
          >
            <ScaleFade initialScale={0.5} in={form.queryTarget.length !== 0}>
              <SubmitButton />
            </ScaleFade>
          </Flex>
        </FormRow>
      </chakra.form>
    </FormProvider>
  );
};

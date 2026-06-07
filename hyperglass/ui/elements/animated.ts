import { chakra } from '@chakra-ui/react';
import { motion } from 'framer-motion';

import type { BoxProps } from '@chakra-ui/react';
import type { MotionProps, Transition } from 'framer-motion';

type MCComponent = Parameters<typeof chakra>[0];
type MCOptions = Parameters<typeof chakra>[1];
type MakeMotionProps<P extends BoxProps> = React.PropsWithChildren<
  Omit<P, 'transition'> & Omit<MotionProps, 'transition'> & { transition?: Transition }
>;

/**
 * Return type of `motionChakra`. Self-defined replacement for framer-motion's
 * `CustomDomComponent` (removed from the public types in v11.x), mirroring its
 * shape so the signature survives framer-motion type churn.
 */
type MotionChakraComponent<P extends BoxProps> = React.ForwardRefExoticComponent<
  MakeMotionProps<P> & React.RefAttributes<HTMLElement>
>;

/**
 * Combine `chakra` and `motion` factories.
 *
 * Chakra and framer-motion both declare a `transition` prop (CSS string vs.
 * animation config), so the combined component's props are re-declared with
 * chakra's omitted — the cast below is deliberate and is what makes the
 * merged component usable without per-call-site suppressions.
 *
 * @param component Component or string
 * @param options `chakra` options
 * @returns Chakra component with motion props.
 */
export function motionChakra<P extends BoxProps = BoxProps>(
  component: MCComponent,
  options?: MCOptions,
): MotionChakraComponent<P> {
  return motion(chakra(component, options)) as unknown as MotionChakraComponent<P>;
}

export const AnimatedDiv = motionChakra('div');

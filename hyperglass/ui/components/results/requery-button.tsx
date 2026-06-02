import { Button, Tooltip } from '@chakra-ui/react';
import { useEffect, useRef, useState } from 'react';
import { useConfig } from '~/context';
import { DynamicIcon } from '~/elements';
import { useStrf } from '~/hooks';

interface RequeryButtonProps {
  onRequery: () => void;
  lastResponseAt: number;
  isDisabled?: boolean;
}

export const RequeryButton = (props: RequeryButtonProps): JSX.Element => {
  const { onRequery, lastResponseAt, isDisabled = false } = props;

  const { cache, web } = useConfig();
  const refreshMinIntervalMs = cache.refreshMinInterval * 1000;
  const strF = useStrf();

  const getRemainingMs = (): number => {
    const elapsed = Date.now() - lastResponseAt;
    return Math.max(0, refreshMinIntervalMs - elapsed);
  };

  const [remainingMs, setRemainingMs] = useState<number>(getRemainingMs);

  // Reset and start countdown whenever lastResponseAt changes.
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Recompute immediately when lastResponseAt changes.
    const initial = getRemainingMs();
    setRemainingMs(initial);

    if (initial <= 0) {
      return;
    }

    intervalRef.current = setInterval(() => {
      const remaining = getRemainingMs();
      setRemainingMs(remaining);
      if (remaining <= 0 && intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }, 1000);

    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
    // getRemainingMs is intentionally omitted from deps: it's a stable inline
    // closure that only reads lastResponseAt and refreshMinIntervalMs, both of
    // which ARE in the dep array — adding the function itself would cause an
    // infinite re-registration loop.
  }, [lastResponseAt, refreshMinIntervalMs]); // eslint-disable-line react-hooks/exhaustive-deps

  const isCoolingDown = remainingMs > 0;
  const remainingSeconds = Math.ceil(remainingMs / 1000);

  const tooltipLabel = isCoolingDown
    ? strF(web.text.refreshCooldown, { seconds: remainingSeconds })
    : web.text.requeryTooltip;

  return (
    <Tooltip hasArrow shouldWrapChildren label={tooltipLabel} placement="top">
      <Button
        mx={1}
        size="sm"
        zIndex="1"
        variant="ghost"
        aria-label={web.text.requeryTooltip}
        onClick={onRequery}
        isDisabled={isCoolingDown || isDisabled}
        colorScheme="secondary"
      >
        <DynamicIcon icon={{ fi: 'FiRepeat' }} boxSize="16px" />
      </Button>
    </Tooltip>
  );
};

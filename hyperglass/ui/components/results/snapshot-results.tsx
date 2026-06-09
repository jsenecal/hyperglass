import { Accordion } from '@chakra-ui/react';
import { AnimatedDiv } from '~/elements';
import { Result } from './individual';

export interface SnapshotResultsItem {
  queryLocation: string;
  snapshot: ResultSnapshot;
}

interface SnapshotResultsProps {
  items: SnapshotResultsItem[];
  /** Show each result's ShareButton (history-open); default false (share page). */
  showShare?: boolean;
  /** Called with the minted share id after a successful share; only meaningful for single-device entries. */
  onShared?: (shareId: string) => void;
}

export const SnapshotResults = (props: SnapshotResultsProps): JSX.Element => {
  const { items, showShare = false, onShared } = props;
  return (
    <AnimatedDiv
      p={0}
      my={4}
      w="100%"
      mx="auto"
      rounded="lg"
      textAlign="left"
      borderWidth="1px"
      overflow="hidden"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, y: 300 }}
      transition={{ duration: 0.3 }}
      animate={{ opacity: 1, y: 0 }}
    >
      <Accordion defaultIndex={items.map((_, i) => i)} allowMultiple>
        {items.map((item, index) => (
          <Result
            key={item.queryLocation}
            index={index}
            queryLocation={item.queryLocation}
            snapshot={item.snapshot}
            readOnly
            showShare={showShare}
            onShared={onShared}
          />
        ))}
      </Accordion>
    </AnimatedDiv>
  );
};

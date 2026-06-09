import { useConfig } from '~/context';
import { FloatingBackButton } from '~/elements';
import { useFormState } from '~/hooks';

interface ResetButtonProps {
  developerMode: boolean;
  resetForm(): void;
}

export const ResetButton = (props: ResetButtonProps): JSX.Element => {
  const { developerMode, resetForm } = props;
  const status = useFormState(s => s.status);
  const { web } = useConfig();
  return (
    <FloatingBackButton
      isVisible={status === 'results'}
      onClick={resetForm}
      label={web.text.historyBack}
      raised={developerMode}
    />
  );
};

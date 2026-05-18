import { Label } from '@patternfly/react-core';
import type { Accelerator } from '../api/types';

const colors: Record<string, 'blue' | 'orange' | 'grey'> = {
  xeon6: 'blue',
  gaudi: 'orange',
  local: 'grey',
};

const labels: Record<string, string> = {
  xeon6: 'Xeon 6',
  gaudi: 'Gaudi',
  local: 'Local',
};

export default function HardwareBadge({ accelerator }: { accelerator: Accelerator | string }) {
  return (
    <Label color={colors[accelerator] || 'grey'}>
      {labels[accelerator] || accelerator}
    </Label>
  );
}

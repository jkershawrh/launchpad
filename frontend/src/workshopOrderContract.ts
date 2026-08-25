export const MAX_WORKSHOP_SEATS = 25;

export function validateSeatCount(value: number): string | null {
  if (!Number.isInteger(value)) return 'Seat count must be a whole number.';
  if (value < 1 || value > MAX_WORKSHOP_SEATS) {
    return `Seat count must be between 1 and ${MAX_WORKSHOP_SEATS}.`;
  }
  return null;
}

export function workshopReadiness(ready: number, requested: number): number {
  if (requested < 1) return 0;
  return Math.round((ready / requested) * 100);
}

export function workshopProgressLabel(
  status: string,
  ready: number,
  reclaimed: number,
  requested: number,
): string {
  if (status === 'reclaiming') return `${reclaimed}/${requested} seats reclaimed`;
  if (status === 'provisioning' && ready === requested) {
    return `${requested}/${requested} seats provisioned · verifying collective stability`;
  }
  if (status === 'provisioning' || status === 'queued') {
    return `${ready}/${requested} seats individually ready`;
  }
  return `${ready}/${requested} seats ready`;
}

export function reclaimActionLabel(status: string): string {
  return ['queued', 'provisioning'].includes(status)
    ? 'Cancel provisioning'
    : 'Reclaim workshop';
}

export const MAX_WORKSHOP_SEATS = 25;

export function validateSeatCount(value: number, maximum = MAX_WORKSHOP_SEATS): string | null {
  if (!Number.isInteger(value)) return 'Seat count must be a whole number.';
  if (value < 1 || value > maximum) {
    return `Seat count must be between 1 and ${maximum}.`;
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

type WorkshopAccess = {
  exposure_policy?: 'internal' | 'public_code';
  public_url?: string;
};

type WorkshopSeatAccess = {
  showroom_url?: string;
  lab_url?: string;
};

export function workshopSeatAccess(
  workshop: WorkshopAccess,
  seat: WorkshopSeatAccess,
): { url: string; label: string; public: boolean } | null {
  if (workshop.exposure_policy === 'public_code' && workshop.public_url) {
    return {
      url: workshop.public_url,
      label: 'Open participant portal',
      public: true,
    };
  }
  const url = seat.showroom_url || seat.lab_url;
  return url ? { url, label: 'Open Showroom', public: false } : null;
}

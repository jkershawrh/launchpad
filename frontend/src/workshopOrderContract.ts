export function validateSeatCount(value: number): string | null {
  if (!Number.isInteger(value)) return 'Seat count must be a whole number.';
  if (value < 1 || value > 100) return 'Seat count must be between 1 and 100.';
  return null;
}

export function workshopReadiness(ready: number, requested: number): number {
  if (requested < 1) return 0;
  return Math.round((ready / requested) * 100);
}

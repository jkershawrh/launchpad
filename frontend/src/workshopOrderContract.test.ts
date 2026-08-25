import { describe, expect, it } from 'vitest';
import {
  MAX_WORKSHOP_SEATS,
  reclaimActionLabel,
  validateSeatCount,
  workshopProgressLabel,
  workshopReadiness,
} from './workshopOrderContract';

describe('workshop order contract', () => {
  it('accepts supported seat counts', () => {
    expect(validateSeatCount(1)).toBeNull();
    expect(validateSeatCount(20)).toBeNull();
    expect(validateSeatCount(25)).toBeNull();
    expect(MAX_WORKSHOP_SEATS).toBe(25);
  });

  it('rejects unsafe seat counts', () => {
    expect(validateSeatCount(0)).toMatch(/between 1 and 25/);
    expect(validateSeatCount(26)).toMatch(/between 1 and 25/);
    expect(validateSeatCount(2.5)).toMatch(/whole number/);
  });

  it('calculates instructor readiness', () => {
    expect(workshopReadiness(18, 20)).toBe(90);
  });

  it('describes collective stability and cancellation phases', () => {
    expect(workshopProgressLabel('provisioning', 25, 0, 25)).toMatch(/verifying collective stability/);
    expect(workshopProgressLabel('reclaiming', 0, 12, 25)).toBe('12/25 seats reclaimed');
    expect(reclaimActionLabel('provisioning')).toBe('Cancel provisioning');
    expect(reclaimActionLabel('ready')).toBe('Reclaim workshop');
  });
});

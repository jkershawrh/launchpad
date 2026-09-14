import { describe, expect, it } from 'vitest';
import {
  MAX_WORKSHOP_SEATS,
  reclaimActionLabel,
  validateSeatCount,
  workshopProgressLabel,
  workshopReadiness,
  workshopSeatAccess,
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

  it('enforces a catalog certification seat ceiling', () => {
    expect(validateSeatCount(1, 1)).toBeNull();
    expect(validateSeatCount(2, 1)).toMatch(/between 1 and 1/);
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

  it('never exposes a private seat route for a public workshop', () => {
    expect(workshopSeatAccess(
      {
        public_url: 'https://labs.smg-helix.ai/labs/multi-agent-quickstart-order-1',
        exposure_policy: 'public_code',
      },
      {
        showroom_url: 'https://showroom-seat.apps.brutus.fm2aihpcsed.com',
        lab_url: 'https://multi-agent-ui-seat.apps.brutus.fm2aihpcsed.com',
      },
    )).toEqual({
      url: 'https://labs.smg-helix.ai/labs/multi-agent-quickstart-order-1',
      label: 'Open participant portal',
      public: true,
    });
  });

  it('retains direct Showroom access for an internal workshop', () => {
    expect(workshopSeatAccess(
      { exposure_policy: 'internal' },
      {
        showroom_url: 'https://showroom-seat.apps.brutus.fm2aihpcsed.com',
        lab_url: 'https://multi-agent-ui-seat.apps.brutus.fm2aihpcsed.com',
      },
    )).toEqual({
      url: 'https://showroom-seat.apps.brutus.fm2aihpcsed.com',
      label: 'Open Showroom',
      public: false,
    });
  });
});

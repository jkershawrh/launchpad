import { describe, expect, it } from 'vitest';
import { validateSeatCount, workshopReadiness } from './workshopOrderContract';

describe('workshop order contract', () => {
  it('accepts supported seat counts', () => {
    expect(validateSeatCount(1)).toBeNull();
    expect(validateSeatCount(20)).toBeNull();
    expect(validateSeatCount(20)).toBeNull();
  });

  it('rejects unsafe seat counts', () => {
    expect(validateSeatCount(0)).toMatch(/between 1 and 20/);
    expect(validateSeatCount(21)).toMatch(/between 1 and 20/);
    expect(validateSeatCount(2.5)).toMatch(/whole number/);
  });

  it('calculates instructor readiness', () => {
    expect(workshopReadiness(18, 20)).toBe(90);
  });
});

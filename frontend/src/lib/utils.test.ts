import { describe, expect, it } from 'vitest';
import {
  formatDisplayValue,
  formatDuration,
  formatManagementSummary,
  formatTemporalBucket,
  humanizeField
} from './utils';

describe('result presentation formatting', () => {
  it('counts execution duration in seconds from the beginning', () => {
    expect(formatDuration(
      '2026-07-31T08:00:00.000Z',
      '2026-07-31T08:00:00.900Z',
      'en-US'
    )).toBe('0 sec');
    expect(formatDuration(
      '2026-07-31T08:00:00.000Z',
      '2026-07-31T08:01:02.000Z',
      'en-US'
    )).toBe('1 min 2 sec');
  });

  it('formats governed decimal values without machine precision noise', () => {
    expect(formatDisplayValue('6525519.300000', 'en-US', 'DECIMAL(20,6)'))
      .toBe('6,525,519.3');
    expect(formatDisplayValue('0E-10', 'en-US', 'DECIMAL(20,10)')).toBe('0');
    expect(formatDisplayValue('0.0250000000', 'en-US', 'DECIMAL(20,10)')).toBe('0.025');
    expect(formatDisplayValue('6525519.300000', 'en-US')).toBe('6,525,519.3');
    expect(formatDisplayValue('0E-10', 'en-US')).toBe('0');
  });

  it('humanizes technical result aliases', () => {
    expect(humanizeField('total_sales', 'en-US')).toBe('Total sales');
    expect(humanizeField('AVG_DISCOUNT_RATE', 'en-US')).toBe('Average discount rate');
    expect(humanizeField('Monthly Call Count', 'en-US')).toBe('Monthly call count');
  });

  it('formats governed temporal buckets at their requested granularity', () => {
    expect(formatTemporalBucket('2026-01-01T00:00:00', 'MONTH')).toBe('2026-01');
    expect(formatTemporalBucket('2026-04-01T00:00:00', 'QUARTER')).toBe('2026-Q2');
    expect(formatTemporalBucket('2026-01-01T00:00:00', 'YEAR')).toBe('2026');
  });

  it('removes provider template labels from management summaries', () => {
    expect(formatManagementSummary(
      '**Decision Summary** Web led sales. **Approved Warnings** None'
    )).toBe('Web led sales.');
  });
});

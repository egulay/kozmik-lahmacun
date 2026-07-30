import { describe, expect, it } from 'vitest';
import { formatDisplayValue, humanizeField } from './utils';

describe('result presentation formatting', () => {
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
  });
});

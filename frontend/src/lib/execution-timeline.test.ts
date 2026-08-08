import { describe, expect, it } from 'vitest';
import type { StatusHistory } from '$lib/types';
import { lifecycleTimeline } from '$lib/execution-timeline';

function event(messageCode: string, occurredAt: string, progressPercent: number): StatusHistory {
  return {
    eventId: messageCode + occurredAt,
    stage: messageCode === 'EXECUTION_ML_TRAINING' ? 'TRAINING' : 'TRAINING',
    status: 'RUNNING',
    progressPercent,
    messageCode,
    occurredAt
  };
}

describe('lifecycleTimeline', () => {
  it('merges Spark samples into the ML training lifecycle row', () => {
    const result = lifecycleTimeline([
      event('EXECUTION_ML_TRAINING', '2026-08-08T09:40:00Z', 40),
      event('EXECUTION_SPARK_PROGRESS', '2026-08-08T09:41:00Z', 55),
      event('EXECUTION_SPARK_PROGRESS', '2026-08-08T09:42:00Z', 70)
    ], 'ML');

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      stage: 'TRAINING',
      messageCode: 'EXECUTION_ML_TRAINING',
      progressPercent: 70,
      occurredAt: '2026-08-08T09:42:00Z'
    });
  });

  it('merges Spark samples into the report running lifecycle row', () => {
    const result = lifecycleTimeline([
      { ...event('EXECUTION_SPARK_RUNNING', '2026-08-08T09:40:00Z', 40), stage: 'RUNNING' },
      { ...event('EXECUTION_SPARK_PROGRESS', '2026-08-08T09:42:00Z', 65), stage: 'RUNNING' }
    ], 'REPORT');

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      stage: 'RUNNING',
      messageCode: 'EXECUTION_SPARK_RUNNING',
      progressPercent: 65
    });
  });
});

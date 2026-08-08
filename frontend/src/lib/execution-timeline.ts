import type { StatusHistory } from '$lib/types';

export function lifecycleTimeline(
  history: StatusHistory[],
  executionType: string
): StatusHistory[] {
  const latestSparkProgress = history
    .filter((item) => item.messageCode === 'EXECUTION_SPARK_PROGRESS')
    .sort((left, right) => Date.parse(right.occurredAt) - Date.parse(left.occurredAt))[0];

  if (!latestSparkProgress) {
    return [...history].sort(
      (left, right) => Date.parse(right.occurredAt) - Date.parse(left.occurredAt)
    );
  }

  const isMl = executionType.toUpperCase().includes('ML');
  const lifecycleCode = isMl ? 'EXECUTION_ML_TRAINING' : 'EXECUTION_SPARK_RUNNING';
  const lifecycleStage = isMl ? 'TRAINING' : 'RUNNING';
  const mergedProgress: StatusHistory = {
    ...latestSparkProgress,
    stage: lifecycleStage,
    messageCode: lifecycleCode
  };

  return history
    .filter((item) =>
      item.messageCode !== 'EXECUTION_SPARK_PROGRESS'
      && item.messageCode !== lifecycleCode
    )
    .concat(mergedProgress)
    .sort((left, right) => Date.parse(right.occurredAt) - Date.parse(left.occurredAt));
}

import { writable } from 'svelte/store';

export const deletingExecutionIds = writable<ReadonlySet<string>>(new Set());

export function beginExecutionDeletion(executionId: string) {
  deletingExecutionIds.update((current) => new Set(current).add(executionId));
}

export function endExecutionDeletion(executionId: string) {
  deletingExecutionIds.update((current) => {
    const next = new Set(current);
    next.delete(executionId);
    return next;
  });
}

export function notifyExecutionDeleted(executionId: string) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent('kozmik:execution-deleted', {
    detail: { executionId }
  }));
}

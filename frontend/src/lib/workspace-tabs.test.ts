import { get } from 'svelte/store';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  openWorkspaceTab,
  reconcileWorkspaceTabs,
  workspaceTabs,
  type WorkspaceTab
} from './workspace-tabs';

function tab(executionId: string, tabType: WorkspaceTab['tabType']): WorkspaceTab {
  return {
    executionId,
    title: executionId,
    kind: 'REPORT',
    status: 'SUCCEEDED',
    tabType
  };
}

describe('workspace tab reconciliation', () => {
  beforeEach(() => {
    sessionStorage.clear();
    workspaceTabs.set([]);
  });

  it('removes tabs whose authoritative resource no longer exists', async () => {
    openWorkspaceTab(tab('existing', 'execution'));
    openWorkspaceTab(tab('removed', 'result'));

    const removed = await reconcileWorkspaceTabs(
      async (candidate) => candidate.executionId === 'existing'
    );

    expect(get(workspaceTabs).map((item) => item.executionId)).toEqual(['existing']);
    expect(removed.map((item) => item.executionId)).toEqual(['removed']);
    expect(JSON.parse(sessionStorage.getItem('kozmik-workspace-tabs') ?? '[]'))
      .toHaveLength(1);
  });

  it('keeps execution and result tabs when both remain authorized', async () => {
    openWorkspaceTab(tab('execution-id', 'execution'));
    openWorkspaceTab(tab('execution-id', 'result'));

    const removed = await reconcileWorkspaceTabs(async () => true);

    expect(removed).toEqual([]);
    expect(get(workspaceTabs)).toHaveLength(2);
  });
});

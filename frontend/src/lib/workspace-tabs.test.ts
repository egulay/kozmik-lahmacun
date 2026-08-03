import { get } from 'svelte/store';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  getWorkspaceView,
  initializeWorkspaceTabs,
  openWorkspaceTab,
  reconcileWorkspaceTabs,
  setWorkspaceView,
  workspaceTabResourceId,
  workspaceTabs,
  type WorkspaceTab
} from './workspace-tabs';

function tab(
  executionId: string,
  tabType: 'execution' | 'result'
): WorkspaceTab {
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
    initializeWorkspaceTabs(crypto.randomUUID());
  });

  it('removes tabs whose authoritative resource no longer exists', async () => {
    openWorkspaceTab(tab('existing', 'execution'));
    openWorkspaceTab(tab('removed', 'result'));

    const removed = await reconcileWorkspaceTabs(
      async (candidate) => workspaceTabResourceId(candidate) === 'existing'
    );

    expect(get(workspaceTabs).map(workspaceTabResourceId)).toEqual(['existing']);
    expect(removed.map(workspaceTabResourceId)).toEqual(['removed']);
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

  it('keeps chat, execution, and result tabs as separate workspace resources', () => {
    openWorkspaceTab({
      threadId: 'thread-id',
      title: 'Conversation',
      tabType: 'chat'
    });
    openWorkspaceTab(tab('execution-id', 'execution'));
    openWorkspaceTab(tab('execution-id', 'result'));

    expect(get(workspaceTabs).map((item) => item.tabType))
      .toEqual(['chat', 'execution', 'result']);
  });

  it('keeps entity detail and application page tabs independently', () => {
    openWorkspaceTab({
      pageId: 'entities',
      title: 'Data Entities',
      tabType: 'page'
    });
    openWorkspaceTab({
      entityId: 'entity-id',
      title: 'Sales Record',
      tabType: 'entity'
    });
    openWorkspaceTab({
      pageId: 'users',
      title: 'Users',
      tabType: 'page'
    });

    expect(get(workspaceTabs).map((item) => item.tabType))
      .toEqual(['page', 'entity', 'page']);
    expect(get(workspaceTabs).map(workspaceTabResourceId))
      .toEqual(['entities', 'entity-id', 'users']);
  });

  it('clears every tab when the backend workspace generation changes', () => {
    initializeWorkspaceTabs('database-generation-1');
    setWorkspaceView('result:one:en', { id: 'one' });
    openWorkspaceTab({
      pageId: 'entities',
      title: 'Data Entities',
      tabType: 'page'
    });
    openWorkspaceTab({
      pageId: 'users',
      title: 'Users',
      tabType: 'page'
    });

    initializeWorkspaceTabs('database-generation-2');

    expect(get(workspaceTabs)).toEqual([]);
    expect(sessionStorage.getItem('kozmik-workspace-generation'))
      .toBe('database-generation-2');
    expect(getWorkspaceView('result:one:en')).toBeUndefined();
  });

  it('keeps a bounded in-memory view cache for flicker-free tab revisits', () => {
    setWorkspaceView('execution:one:en', { status: 'RUNNING' });

    expect(getWorkspaceView<{ status: string }>('execution:one:en'))
      .toEqual({ status: 'RUNNING' });

    for (let index = 0; index < 24; index += 1) {
      setWorkspaceView(`view:${index}`, index);
    }

    expect(getWorkspaceView('execution:one:en')).toBeUndefined();
    expect(getWorkspaceView('view:23')).toBe(23);
  });
});

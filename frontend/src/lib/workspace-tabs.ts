import { browser } from '$app/environment';
import { get, writable } from 'svelte/store';

export interface ExecutionWorkspaceTab {
  executionId: string;
  title: string;
  kind: 'REPORT' | 'ML';
  status: string;
  tabType: 'execution' | 'result';
}

export interface ChatWorkspaceTab {
  threadId: string;
  title: string;
  tabType: 'chat';
}

export interface EntityWorkspaceTab {
  entityId: string;
  title: string;
  tabType: 'entity';
}

export interface PageWorkspaceTab {
  pageId: 'executions' | 'results' | 'entities' | 'users';
  title: string;
  tabType: 'page';
}

export type WorkspaceTab =
  | ExecutionWorkspaceTab
  | ChatWorkspaceTab
  | EntityWorkspaceTab
  | PageWorkspaceTab;

const storageKey = 'kozmik-workspace-tabs';
const generationStorageKey = 'kozmik-workspace-generation';

function restoreTabs(): WorkspaceTab[] {
  if (!browser) return [];
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) ?? '[]');
    if (!Array.isArray(value)) return [];
    return value.filter((tab): tab is WorkspaceTab => {
      if (!tab || typeof tab.title !== 'string') return false;
      if (tab.tabType === 'chat') return typeof tab.threadId === 'string';
      if (tab.tabType === 'entity') return typeof tab.entityId === 'string';
      if (tab.tabType === 'page') {
        return ['executions', 'results', 'entities', 'users'].includes(tab.pageId);
      }
      return typeof tab.executionId === 'string'
        && (tab.kind === 'REPORT' || tab.kind === 'ML')
        && typeof tab.status === 'string'
        && (tab.tabType === 'execution' || tab.tabType === 'result');
    }).slice(-12);
  } catch {
    return [];
  }
}

export const workspaceTabs = writable<WorkspaceTab[]>(restoreTabs());

if (browser) {
  workspaceTabs.subscribe((tabs) => {
    sessionStorage.setItem(storageKey, JSON.stringify(tabs));
  });
}

export function initializeWorkspaceTabs(workspaceGeneration: string) {
  if (!browser) return;
  const storedGeneration = sessionStorage.getItem(generationStorageKey);
  if (storedGeneration !== workspaceGeneration) {
    workspaceTabs.set([]);
    sessionStorage.setItem(generationStorageKey, workspaceGeneration);
  }
}

export function openWorkspaceTab(tab: WorkspaceTab) {
  workspaceTabs.update((tabs) => {
    const key = workspaceTabKey(tab);
    const existingIndex = tabs.findIndex((item) => workspaceTabKey(item) === key);
    if (existingIndex < 0) return [...tabs, tab].slice(-12);
    return tabs.map((item, index) => index === existingIndex ? tab : item);
  });
}

export function closeWorkspaceTab(tabType: WorkspaceTab['tabType'], resourceId: string) {
  workspaceTabs.update((tabs) =>
    tabs.filter((item) =>
      item.tabType !== tabType || workspaceTabResourceId(item) !== resourceId
    )
  );
}

export function closeExecutionWorkspace(executionId: string) {
  workspaceTabs.update((tabs) => tabs.filter((item) =>
    (item.tabType !== 'execution' && item.tabType !== 'result')
      || item.executionId !== executionId
  ));
}

export function workspaceTabResourceId(tab: WorkspaceTab): string {
  if (tab.tabType === 'chat') return tab.threadId;
  if (tab.tabType === 'entity') return tab.entityId;
  if (tab.tabType === 'page') return tab.pageId;
  return tab.executionId;
}

export function workspaceTabKey(tab: WorkspaceTab): string {
  return `${tab.tabType}:${workspaceTabResourceId(tab)}`;
}

export async function reconcileWorkspaceTabs(
  exists: (tab: WorkspaceTab) => Promise<boolean>
): Promise<WorkspaceTab[]> {
  const tabs = get(workspaceTabs);
  const checks = await Promise.all(tabs.map(async (tab) => ({
    tab,
    exists: await exists(tab)
  })));
  const retained = checks.filter((check) => check.exists).map((check) => check.tab);
  workspaceTabs.set(retained);
  return tabs.filter((tab) => !retained.some(
    (item) => workspaceTabKey(item) === workspaceTabKey(tab)
  ));
}

import { browser } from '$app/environment';
import { writable } from 'svelte/store';

export interface WorkspaceTab {
  executionId: string;
  title: string;
  kind: 'REPORT' | 'ML';
  status: string;
  tabType: 'execution' | 'result';
}

const storageKey = 'kozmik-workspace-tabs';

function restoreTabs(): WorkspaceTab[] {
  if (!browser) return [];
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) ?? '[]');
    if (!Array.isArray(value)) return [];
    return value.filter((tab): tab is WorkspaceTab =>
      tab
      && typeof tab.executionId === 'string'
      && typeof tab.title === 'string'
      && (tab.kind === 'REPORT' || tab.kind === 'ML')
      && typeof tab.status === 'string'
      && (tab.tabType === 'execution' || tab.tabType === 'result')
    ).slice(-12);
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

export function openWorkspaceTab(tab: WorkspaceTab) {
  workspaceTabs.update((tabs) => {
    const key = `${tab.tabType}:${tab.executionId}`;
    const existingIndex = tabs.findIndex(
      (item) => `${item.tabType}:${item.executionId}` === key
    );
    if (existingIndex < 0) return [...tabs, tab].slice(-12);
    return tabs.map((item, index) => index === existingIndex ? tab : item);
  });
}

export function closeWorkspaceTab(tabType: WorkspaceTab['tabType'], executionId: string) {
  workspaceTabs.update((tabs) =>
    tabs.filter((item) => item.tabType !== tabType || item.executionId !== executionId)
  );
}

export function closeExecutionWorkspace(executionId: string) {
  workspaceTabs.update((tabs) => tabs.filter((item) => item.executionId !== executionId));
}

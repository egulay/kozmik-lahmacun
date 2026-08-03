import { get } from 'svelte/store';
import { api } from './api';
import { locale } from './i18n';
import type { ColumnDefinition, EntitySummary, Execution, ExecutionResult } from './types';
import {
  getWorkspaceView,
  setWorkspaceView,
  type WorkspaceTab
} from './workspace-tabs';

export async function preloadWorkspaceTab(tab: WorkspaceTab): Promise<void> {
  const language = get(locale);
  if (tab.tabType === 'chat') {
    const key = `chat:${tab.threadId}`;
    if (getWorkspaceView(key)) return;
    const response = await api.messagePage(tab.threadId, 0, 20);
    setWorkspaceView(key, {
      messages: response.items,
      page: response.page,
      last: response.last
    });
    return;
  }
  if (tab.tabType === 'entity') {
    const key = `entity:${tab.entityId}:${language}`;
    if (getWorkspaceView(key)) return;
    const [entity, columns] = await Promise.all([
      api.entity(tab.entityId),
      api.entityColumns(tab.entityId, 0, 20)
    ]);
    setWorkspaceView(key, {
      entity,
      columns: columns.items,
      columnPage: columns.page,
      columnTotalElements: columns.totalElements,
      columnTotalPages: columns.totalPages,
      ingestionActive: entity.latestImportStatus === 'INGESTING',
      ingestionStatus: entity.latestImportStatus ?? '',
      latestBatchRows: entity.latestBatchRowCount ?? null,
      lastCheckpoint: entity.lastCheckpointAt ?? null
    });
    return;
  }
  if (tab.tabType === 'execution') {
    const key = `execution:${tab.executionId}:${language}`;
    if (getWorkspaceView(key)) return;
    const execution = await api.execution(tab.executionId);
    const localizedEntity = await api.entity(execution.entityId).catch(() => null);
    setWorkspaceView(key, { execution, localizedEntity });
    return;
  }
  if (tab.tabType === 'result') {
    await preloadResult(tab.executionId, language);
    return;
  }
  if (tab.tabType === 'page') await preloadPage(tab.pageId, language);
}

async function preloadResult(executionId: string, language: string): Promise<void> {
  const key = `result:${executionId}:${language}`;
  if (getWorkspaceView(key)) return;
  const execution = await api.execution(executionId);
  const [result, localizedEntity, schema] = await Promise.all([
    execution.status === 'SUCCEEDED' ? api.result(executionId) : Promise.resolve(null),
    api.entity(execution.entityId).catch(() => null),
    api.entitySchema(execution.entityId).catch(() => null)
  ]);
  setWorkspaceView(key, resultView(execution, result, localizedEntity, schema?.columns ?? []));
}

async function preloadPage(pageId: string, language: string): Promise<void> {
  const key = `page:${pageId}:${language}`;
  if (getWorkspaceView(key)) return;
  if (pageId === 'entities') {
    const response = await api.entityPage(0, 20);
    setWorkspaceView(key, pageView('entities', response.items, response));
  } else if (pageId === 'executions') {
    const response = await api.executionPage({ page: 0, size: 20 });
    setWorkspaceView(key, pageView('executions', response.items, response));
  } else if (pageId === 'results') {
    const response = await api.executionPage({
      page: 0,
      size: 20,
      statuses: ['SUCCEEDED', 'FAILED']
    });
    setWorkspaceView(key, pageView('results', response.items, response));
  }
}

function pageView(
  property: 'entities' | 'executions' | 'results',
  items: EntitySummary[] | Execution[],
  page: { page: number; size: number; totalElements: number; totalPages: number }
) {
  return {
    [property]: items,
    pageNumber: page.page,
    pageSize: page.size,
    totalElements: page.totalElements,
    totalPages: page.totalPages
  };
}

function resultView(
  execution: Execution,
  result: ExecutionResult | null,
  localizedEntity: EntitySummary | null,
  localizedColumns: ColumnDefinition[]
) {
  return {
    result,
    previewData: result?.preview ?? null,
    previewPage: result?.previewPage ?? 0,
    previewSize: result?.previewSize ?? 20,
    previewTotalElements: result?.previewTotalElements ?? 0,
    previewTotalPages: result?.previewTotalPages ?? 0,
    execution,
    localizedEntity,
    localizedColumns
  };
}

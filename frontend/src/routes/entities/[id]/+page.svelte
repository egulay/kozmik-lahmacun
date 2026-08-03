<script lang="ts">
  import { page } from '$app/stores';
  import { ArrowLeft, Database, LoaderCircle } from '@lucide/svelte';
  import { api } from '$lib/api';
  import { locale, statusLabel, t } from '$lib/i18n';
  import type { ColumnDefinition, EntitySummary } from '$lib/types';
  import * as Card from '$lib/components/ui/card/index.js';
  import { Badge } from '$lib/components/ui/badge/index.js';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Table from '$lib/components/ui/table/index.js';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import StateView from '$lib/components/StateView.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { DurableEventStream } from '$lib/sse';
  import ServerPagination from '$lib/components/ServerPagination.svelte';
  import { getWorkspaceView, openWorkspaceTab, setWorkspaceView } from '$lib/workspace-tabs';

  let entity = $state<EntitySummary | null>(null);
  let columns = $state<ColumnDefinition[]>([]);
  let columnPage = $state(0);
  let columnSize = $state(20);
  let columnTotalElements = $state(0);
  let columnTotalPages = $state(0);
  let loading = $state(true);
  let error = $state('');
  let stream: DurableEventStream | undefined;
  let reloadTimer: ReturnType<typeof setTimeout> | undefined;
  let completionTimer: ReturnType<typeof setTimeout> | undefined;
  let activityHoldUntil = 0;
  let ingestionActive = $state(false);
  let ingestionStatus = $state('');
  let latestBatchRows = $state<number | null>(null);
  let lastCheckpoint = $state<string | null>(null);
  let activeEntityId = '';
  let loadSequence = 0;
  const STREAM_IDLE_COMPLETION_MS = 10_000;
  type EntityView = {
    entity: EntitySummary;
    columns: ColumnDefinition[];
    columnPage: number;
    columnTotalElements: number;
    columnTotalPages: number;
    ingestionActive: boolean;
    ingestionStatus: string;
    latestBatchRows: number | null;
    lastCheckpoint: string | null;
  };

  $effect(() => {
    const id = $page.params.id;
    if (!id) return;
    activeEntityId = id;
    loadSequence += 1;
    closeEntityResources();
    const cached = getWorkspaceView<EntityView>(`entity:${id}:${$locale}`);
    entity = cached?.entity ?? null;
    columns = cached?.columns ?? [];
    columnPage = cached?.columnPage ?? 0;
    columnTotalElements = cached?.columnTotalElements ?? 0;
    columnTotalPages = cached?.columnTotalPages ?? 0;
    ingestionActive = cached?.ingestionActive ?? false;
    ingestionStatus = cached?.ingestionStatus ?? '';
    latestBatchRows = cached?.latestBatchRows ?? null;
    lastCheckpoint = cached?.lastCheckpoint ?? null;
    error = '';
    loading = !cached;
    void load(!cached, cached?.columnPage ?? 0, id).then(() => {
      if (activeEntityId === id && entity?.id === id) connect(id);
    });
    return () => {
      if (activeEntityId === id) closeEntityResources();
    };
  });

  function closeEntityResources() {
    stream?.close();
    stream = undefined;
    if (reloadTimer) clearTimeout(reloadTimer);
    reloadTimer = undefined;
    if (completionTimer) clearTimeout(completionTimer);
    completionTimer = undefined;
    activityHoldUntil = 0;
  }

  async function load(
    showLoading = true,
    targetColumnPage = columnPage,
    id = activeEntityId
  ) {
    const sequence = ++loadSequence;
    if (showLoading) loading = true;
    try {
      const [loadedEntity, columnResponse] = await Promise.all([
        api.entity(id),
        api.entityColumns(id, targetColumnPage, columnSize)
      ]);
      if (id !== activeEntityId || sequence !== loadSequence) return;
      entity = loadedEntity;
      openWorkspaceTab({
        entityId: loadedEntity.id,
        title: loadedEntity.name,
        tabType: 'entity'
      });
      columns = columnResponse.items;
      columnPage = columnResponse.page;
      columnTotalElements = columnResponse.totalElements;
      columnTotalPages = columnResponse.totalPages;
      if (!completionTimer && Date.now() >= activityHoldUntil) {
        ingestionStatus = loadedEntity.latestImportStatus ?? '';
        ingestionActive = ingestionStatus === 'INGESTING';
      }
      latestBatchRows = loadedEntity.latestBatchRowCount ?? null;
      lastCheckpoint = loadedEntity.lastCheckpointAt ?? null;
      setWorkspaceView<EntityView>(`entity:${id}:${$locale}`, {
        entity: loadedEntity,
        columns: columnResponse.items,
        columnPage: columnResponse.page,
        columnTotalElements: columnResponse.totalElements,
        columnTotalPages: columnResponse.totalPages,
        ingestionActive,
        ingestionStatus,
        latestBatchRows: loadedEntity.latestBatchRowCount ?? null,
        lastCheckpoint: loadedEntity.lastCheckpointAt ?? null
      });
      error = '';
    } catch {
      if (id === activeEntityId && sequence === loadSequence) {
        error = $t('apiUnavailable');
      }
    } finally {
      if (showLoading && id === activeEntityId && sequence === loadSequence) {
        loading = false;
      }
    }
  }

  function changeColumnSize(value: number) {
    columnSize = value;
    void load(true, 0);
  }

  function connect(id: string) {
    stream?.close();
    stream = new DurableEventStream(`/api/entities/${id}/ingestion-stream`, {
      onReconnect: () => {
        if (activeEntityId === id) void load(false, columnPage, id);
      },
      onEvent: (event, name) => {
        if (activeEntityId !== id) return;
        let payload: Record<string, unknown> = {};
        try { payload = JSON.parse(event.data); } catch { return; }
        if (name === 'ingestion-failed') {
          if (completionTimer) clearTimeout(completionTimer);
          completionTimer = undefined;
          activityHoldUntil = 0;
          ingestionActive = false;
          ingestionStatus = 'FAILED';
        } else if (name === 'ingestion-completed') {
          scheduleCompletedStatus(payload.ingestionKind === 'STREAM');
        } else {
          if (completionTimer) clearTimeout(completionTimer);
          completionTimer = undefined;
          activityHoldUntil = Date.now() + STREAM_IDLE_COMPLETION_MS;
          ingestionActive = true;
          ingestionStatus = 'INGESTING';
        }
        if (typeof payload.batchRowCount === 'number') {
          latestBatchRows = payload.batchRowCount;
        }
        if (
          name === 'ingestion-completed'
          && typeof payload.occurredAt === 'string'
        ) {
          lastCheckpoint = payload.occurredAt;
        }
        scheduleAuthoritativeReload(id);
      }
    });
    stream.connect();
  }

  function scheduleCompletedStatus(streamChunk: boolean) {
    if (completionTimer) clearTimeout(completionTimer);
    if (!streamChunk) {
      completionTimer = undefined;
      activityHoldUntil = 0;
      ingestionActive = false;
      ingestionStatus = 'COMPLETED';
      void load(false);
      return;
    }

    activityHoldUntil = Date.now() + STREAM_IDLE_COMPLETION_MS;
    ingestionActive = true;
    ingestionStatus = 'INGESTING';
    completionTimer = setTimeout(() => {
      completionTimer = undefined;
      activityHoldUntil = 0;
      ingestionActive = false;
      ingestionStatus = 'COMPLETED';
      void load(false);
    }, STREAM_IDLE_COMPLETION_MS);
  }

  function scheduleAuthoritativeReload(id: string) {
    if (reloadTimer) return;
    reloadTimer = setTimeout(() => {
      reloadTimer = undefined;
      if (activeEntityId === id) void load(false, columnPage, id);
    }, 1_000);
  }
</script>

<PageHeader title={entity?.name ?? $t('entity')} description={entity?.description}>
  {#snippet actions()}<Button href="/entities" variant="outline" size="sm"><ArrowLeft size={16} />{$t('back')}</Button>{/snippet}
</PageHeader>
<StateView loading={loading && !entity} {error} onretry={load} />
{#if entity}
  <Card.Root class="mb-4">
    <Card.Header class="flex-row items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <span class="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          {#if ingestionActive}
            <LoaderCircle class="animate-spin" size={20} />
          {:else}
            <Database size={20} />
          {/if}
        </span>
        <div>
          <Card.Description>{$t('ingestionActivity')}</Card.Description>
          <Card.Title class="text-base">
            {ingestionStatus || entity.latestImportStatus
              ? statusLabel(ingestionStatus || entity.latestImportStatus || 'UNKNOWN', $locale)
              : '—'}
          </Card.Title>
        </div>
      </div>
      <StatusBadge status={ingestionStatus || entity.latestImportStatus || 'UNKNOWN'} />
    </Card.Header>
    <Card.Content class="grid gap-4 sm:grid-cols-3">
      <div>
        <p class="text-xs text-muted-foreground">{$t('governedRows')}</p>
        <strong class="text-lg">
          {entity.governedRowCount == null
            ? '—'
            : new Intl.NumberFormat($locale === 'tr' ? 'tr-TR' : 'en-US')
                .format(entity.governedRowCount)}
        </strong>
      </div>
      <div>
        <p class="text-xs text-muted-foreground">{$t('latestBatch')}</p>
        <strong class="text-lg">
          {latestBatchRows == null
            ? '—'
            : `${new Intl.NumberFormat($locale === 'tr' ? 'tr-TR' : 'en-US')
                .format(latestBatchRows)}`}
        </strong>
      </div>
      <div>
        <p class="text-xs text-muted-foreground">{$t('lastCheckpoint')}</p>
        <strong class="text-sm">
          {lastCheckpoint
            ? new Date(lastCheckpoint).toLocaleString($locale === 'tr' ? 'tr-TR' : 'en-US')
            : '—'}
        </strong>
      </div>
    </Card.Content>
  </Card.Root>
  <Card.Root>
    <Card.Header>
      <Card.Title>{$t('columns')}</Card.Title>
      <Card.Description>{$t('totalFields')}: {columnTotalElements}</Card.Description>
    </Card.Header>
    <Card.Content
      class={`overflow-x-auto transition-opacity duration-150 ${loading ? 'opacity-60' : ''}`}
      aria-busy={loading}
    ><Table.Root>
      <Table.Header><Table.Row><Table.Head>{$t('columns')}</Table.Head><Table.Head>{$t('dataType')}</Table.Head></Table.Row></Table.Header>
      <Table.Body>{#each columns as column}<Table.Row>
        <Table.Cell><strong>{column.businessName}</strong><code class="mt-1 block text-xs text-muted-foreground">{column.columnName}</code></Table.Cell>
        <Table.Cell><Badge>{column.dataType}</Badge></Table.Cell>
      </Table.Row>{/each}</Table.Body>
    </Table.Root></Card.Content>
    <Card.Footer>
      <ServerPagination
        page={columnPage}
        size={columnSize}
        totalElements={columnTotalElements}
        totalPages={columnTotalPages}
        disabled={loading}
        onPage={(value) => void load(true, value)}
        onSize={changeColumnSize}
      />
    </Card.Footer>
  </Card.Root>
{/if}

<script lang="ts">
  import { onMount } from 'svelte';
  import { ArrowRight, Database } from '@lucide/svelte';
  import { api } from '$lib/api';
  import { locale, statusLabel, t } from '$lib/i18n';
  import type { EntitySummary } from '$lib/types';
  import * as Card from '$lib/components/ui/card/index.js';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import StateView from '$lib/components/StateView.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { DurableEventStream } from '$lib/sse';
  import ServerPagination from '$lib/components/ServerPagination.svelte';
  import { openWorkspaceTab } from '$lib/workspace-tabs';

  let entities = $state<EntitySummary[]>([]);
  let loading = $state(true);
  let error = $state('');
  let stream: DurableEventStream | undefined;
  let reloadTimer: ReturnType<typeof setTimeout> | undefined;
  const completionTimers = new Map<string, ReturnType<typeof setTimeout>>();
  let activeStreamEntities = $state<Record<string, boolean>>({});
  let pageNumber = $state(0);
  let pageSize = $state(20);
  let totalElements = $state(0);
  let totalPages = $state(0);

  onMount(() => {
    openWorkspaceTab({
      pageId: 'entities',
      title: $t('entities'),
      tabType: 'page'
    });
    void load().then(connect);
    return () => {
      stream?.close();
      if (reloadTimer) clearTimeout(reloadTimer);
      for (const timer of completionTimers.values()) clearTimeout(timer);
      completionTimers.clear();
    };
  });

  async function load(showLoading = true, targetPage = pageNumber) {
    if (showLoading) loading = true;
    try {
      const response = await api.entityPage(targetPage, pageSize);
      entities = response.items.map((entity) =>
        activeStreamEntities[entity.id]
          ? { ...entity, latestImportStatus: 'INGESTING' }
          : entity
      );
      pageNumber = response.page;
      totalElements = response.totalElements;
      totalPages = response.totalPages;
      error = '';
    }
    catch { error = $t('apiUnavailable'); }
    finally { if (showLoading) loading = false; }
  }

  function changeSize(value: number) {
    pageSize = value;
    void load(true, 0);
  }

  function connect() {
    stream = new DurableEventStream('/api/entities/ingestion-stream', {
      onReconnect: () => load(false),
      onEvent: (event, name) => {
        if (name !== 'entity-ingestion-changed') return;
        let payload: Record<string, unknown>;
        try { payload = JSON.parse(event.data); } catch { return; }
        const entityId = typeof payload.entityId === 'string' ? payload.entityId : '';
        if (entityId && payload.ingestionKind === 'STREAM') {
          holdStreamActivity(entityId);
        }
        scheduleReload();
      }
    });
    stream.connect();
  }

  function holdStreamActivity(entityId: string) {
    activeStreamEntities = { ...activeStreamEntities, [entityId]: true };
    entities = entities.map((entity) =>
      entity.id === entityId
        ? { ...entity, latestImportStatus: 'INGESTING' }
        : entity
    );

    const existing = completionTimers.get(entityId);
    if (existing) clearTimeout(existing);
    completionTimers.set(entityId, setTimeout(() => {
      completionTimers.delete(entityId);
      const next = { ...activeStreamEntities };
      delete next[entityId];
      activeStreamEntities = next;
      void load(false);
    }, 10_000));
  }

  function scheduleReload() {
    if (reloadTimer) return;
    reloadTimer = setTimeout(() => {
      reloadTimer = undefined;
      void load(false);
    }, 1_000);
  }
</script>

<PageHeader title={$t('entitiesTitle')} description={$t('entitiesBody')} />
<div class="mb-4">
  <StateView loading={loading && entities.length === 0} {error} empty={!loading && !error && !entities.length} onretry={load} />
</div>
{#if !error && (!loading || entities.length)}
  <div class="mb-4 grid gap-4 sm:max-w-sm">
    <Card.Root>
      <Card.Header>
        <Card.Description>{$t('registeredEntities')}</Card.Description>
        <Card.Title class="text-3xl">{totalElements}</Card.Title>
      </Card.Header>
    </Card.Root>
  </div>
{/if}
{#if entities.length}
  <div
    class="grid gap-4 transition-opacity duration-150 sm:grid-cols-2 xl:grid-cols-3"
    class:opacity-60={loading}
    aria-busy={loading}
  >
    {#each entities as entity}
      <a href={`/entities/${entity.id}`} class="block h-full no-underline">
        <Card.Root class="h-full transition-colors hover:bg-muted/50">
          <Card.Header>
            <div class="flex items-start justify-between gap-4">
              <div class="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Database size={20} />
              </div>
              <StatusBadge status={entity.latestImportStatus ?? 'REGISTERED'} />
            </div>
            <Card.Title class="mt-4">{entity.name}</Card.Title>
            <Card.Description>{entity.description}</Card.Description>
          </Card.Header>
          <Card.Content class="grid gap-4 text-sm">
            <div>
              <p class="text-muted-foreground">{$t('importStatus')}</p>
              <p class="font-medium">
                {entity.latestImportStatus
                  ? statusLabel(entity.latestImportStatus, $locale)
                  : '—'}
              </p>
            </div>
            <div>
              <p class="text-muted-foreground">{$t('governedRows')}</p>
              <p class="font-medium">
                {entity.governedRowCount == null
                  ? '—'
                  : new Intl.NumberFormat($locale === 'tr' ? 'tr-TR' : 'en-US').format(entity.governedRowCount)}
              </p>
            </div>
          </Card.Content>
          <Card.Footer>
            <ArrowRight class="ml-auto size-4 text-muted-foreground" aria-hidden="true" />
          </Card.Footer>
        </Card.Root>
      </a>
    {/each}
  </div>
  <ServerPagination
    page={pageNumber}
    size={pageSize}
    {totalElements}
    {totalPages}
    disabled={loading}
    onPage={(value) => void load(true, value)}
    onSize={changeSize}
  />
{/if}

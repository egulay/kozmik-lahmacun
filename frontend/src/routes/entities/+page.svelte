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

  let entities = $state<EntitySummary[]>([]);
  let loading = $state(true);
  let error = $state('');
  let stream: DurableEventStream | undefined;
  let reloadTimer: ReturnType<typeof setTimeout> | undefined;
  let pageNumber = $state(0);
  let pageSize = $state(20);
  let totalElements = $state(0);
  let totalPages = $state(0);
  let registeredStructureCount = $state(0);

  onMount(() => {
    void load().then(connect);
    return () => {
      stream?.close();
      if (reloadTimer) clearTimeout(reloadTimer);
    };
  });

  async function load(showLoading = true, targetPage = pageNumber) {
    if (showLoading) loading = true;
    try {
      const response = await api.entityPage(targetPage, pageSize);
      entities = response.items;
      pageNumber = response.page;
      totalElements = response.totalElements;
      totalPages = response.totalPages;
      registeredStructureCount = response.registeredStructureCount ?? 0;
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
      onEvent: (_event, name) => {
        if (name !== 'entity-ingestion-changed' || reloadTimer) return;
        reloadTimer = setTimeout(() => {
          reloadTimer = undefined;
          void load(false);
        }, 1_000);
      }
    });
    stream.connect();
  }
</script>

<PageHeader title={$t('entitiesTitle')} description={$t('entitiesBody')} />
<div class="mb-4">
  <StateView loading={loading && entities.length === 0} {error} empty={!loading && !error && !entities.length} onretry={load} />
</div>
{#if !error && (!loading || entities.length)}
  <div class="mb-4 grid gap-4 sm:grid-cols-2">
    <Card.Root>
      <Card.Header>
        <Card.Description>{$t('registeredEntities')}</Card.Description>
        <Card.Title class="text-3xl">{totalElements}</Card.Title>
      </Card.Header>
    </Card.Root>
    <Card.Root>
      <Card.Header>
        <Card.Description>{$t('registeredSchemas')}</Card.Description>
        <Card.Title class="text-3xl">{registeredStructureCount}</Card.Title>
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

<script lang="ts">
  import { onMount } from 'svelte';
  import { ChartNoAxesCombined, FlaskConical } from '@lucide/svelte';
  import { api } from '$lib/api';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import * as Card from '$lib/components/ui/card/index.js';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Table from '$lib/components/ui/table/index.js';
  import * as Tooltip from '$lib/components/ui/tooltip/index.js';
  import { locale, t } from '$lib/i18n';
  import type { Execution } from '$lib/types';
  import { formatDate } from '$lib/utils';
  import StateView from '$lib/components/StateView.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import ServerPagination from '$lib/components/ServerPagination.svelte';
  import DeleteExecutionButton from '$lib/components/DeleteExecutionButton.svelte';
  import { openWorkspaceTab } from '$lib/workspace-tabs';

  let results = $state<Execution[]>([]);
  let loading = $state(true);
  let error = $state('');
  let refreshTimer: ReturnType<typeof setInterval> | undefined;
  let pageNumber = $state(0);
  let pageSize = $state(20);
  let totalElements = $state(0);
  let totalPages = $state(0);

  onMount(() => {
    openWorkspaceTab({
      pageId: 'results',
      title: $t('results'),
      tabType: 'page'
    });
    void load();
    refreshTimer = setInterval(() => void load(false), 5_000);
    window.addEventListener('focus', focusRefresh);
    return () => {
      if (refreshTimer) clearInterval(refreshTimer);
      window.removeEventListener('focus', focusRefresh);
    };
  });

  function focusRefresh() {
    void load(false);
  }

  async function load(showLoading = true, targetPage = pageNumber) {
    if (showLoading) loading = true;
    try {
      const response = await api.executionPage({
        page: targetPage, size: pageSize, statuses: ['SUCCEEDED', 'FAILED']
      });
      results = response.items;
      pageNumber = response.page;
      totalElements = response.totalElements;
      totalPages = response.totalPages;
      error = '';
    } catch {
      error = $t('apiUnavailable');
    } finally {
      if (showLoading) loading = false;
    }
  }

  function changeSize(value: number) {
    pageSize = value;
    void load(true, 0);
  }

  function title(execution: Execution) {
    return execution.originalRequest
      ?? `${execution.executionType} · ${execution.entityName ?? execution.entityId}`;
  }

  async function afterDelete() {
    await load(true, results.length === 1 && pageNumber > 0 ? pageNumber - 1 : pageNumber);
  }
</script>

<PageHeader title={$t('results')} description={$t('executionListBody')} />
<Card.Root>
  <Card.Header>
    <Card.Title>{$t('results')}</Card.Title>
    <Card.Description>{$t('resultReady')}</Card.Description>
  </Card.Header>
  <Card.Content>
    <StateView loading={loading && results.length === 0} {error} empty={!loading && !error && results.length === 0} emptyText={$t('noExecutions')} onretry={load} />
    {#if results.length}
      <div
        class="overflow-x-auto transition-opacity duration-150"
        class:opacity-60={loading}
        aria-busy={loading}
      >
        <Table.Root>
          <Table.Header>
            <Table.Row>
              <Table.Head>{$t('type')}</Table.Head>
              <Table.Head>{$t('originalRequest')}</Table.Head>
              <Table.Head>{$t('entity')}</Table.Head>
              <Table.Head>{$t('requestedAt')}</Table.Head>
              <Table.Head>{$t('status')}</Table.Head>
              <Table.Head><span class="sr-only">{$t('delete')}</span></Table.Head>
            </Table.Row>
          </Table.Header>
          <Table.Body>
            {#each results as result}
              {@const description = title(result)}
              <Table.Row>
                <Table.Cell>
                  <span class="flex items-center gap-2">
                    {#if result.executionType.toUpperCase().includes('ML')}
                      <FlaskConical size={16} />
                    {:else}
                      <ChartNoAxesCombined size={16} />
                    {/if}
                    {result.executionType.toUpperCase().includes('ML') ? $t('ml') : $t('report')}
                  </span>
                </Table.Cell>
                <Table.Cell class="max-w-[32rem]">
                  <Tooltip.Provider>
                    <Tooltip.Root>
                      <Tooltip.Trigger>
                        {#snippet child({ props })}
                          <Button
                            {...props}
                            href={`/results/${result.id}`}
                            variant="link"
                            class="block h-auto max-w-full truncate p-0 text-left"
                          >{description}</Button>
                        {/snippet}
                      </Tooltip.Trigger>
                      <Tooltip.Content class="max-w-sm whitespace-normal">{description}</Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </Table.Cell>
                <Table.Cell>{result.entityName ?? result.entityId}</Table.Cell>
                <Table.Cell>{formatDate(result.requestedAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}</Table.Cell>
                <Table.Cell><StatusBadge status={result.status} /></Table.Cell>
                <Table.Cell class="text-right">
                  <DeleteExecutionButton
                    executionId={result.id}
                    compact
                    onDeleted={afterDelete}
                  />
                </Table.Cell>
              </Table.Row>
            {/each}
          </Table.Body>
        </Table.Root>
      </div>
    {/if}
    <ServerPagination
      page={pageNumber}
      size={pageSize}
      {totalElements}
      {totalPages}
      disabled={loading}
      onPage={(value) => void load(true, value)}
      onSize={changeSize}
    />
  </Card.Content>
</Card.Root>

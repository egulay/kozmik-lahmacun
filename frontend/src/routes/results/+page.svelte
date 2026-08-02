<script lang="ts">
  import { onMount } from 'svelte';
  import { ChartNoAxesCombined, FlaskConical, LibraryBig, Search } from '@lucide/svelte';
  import { api } from '$lib/api';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import * as Card from '$lib/components/ui/card/index.js';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Table from '$lib/components/ui/table/index.js';
  import * as Tooltip from '$lib/components/ui/tooltip/index.js';
  import * as Select from '$lib/components/ui/select/index.js';
  import { Input } from '$lib/components/ui/input/index.js';
  import { locale, statusLabel, t } from '$lib/i18n';
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
  let search = $state('');
  let status = $state('ALL');
  let searchTimer: ReturnType<typeof setTimeout> | undefined;

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
        page: targetPage,
        size: pageSize,
        statuses: status === 'ALL' ? ['SUCCEEDED', 'FAILED'] : [status],
        search
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

  function scheduleSearch() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => void load(true, 0), 300);
  }

  function changeStatus(value: string | undefined) {
    if (!value) return;
    status = value;
    void load(true, 0);
  }

  function title(execution: Execution) {
    const entityName = $locale === 'tr'
      ? execution.entityNameTr || execution.entityName || execution.entityId
      : execution.entityName || execution.entityId;
    return execution.originalRequest
      ?? `${execution.executionType} · ${entityName}`;
  }

  async function afterDelete() {
    await load(true, results.length === 1 && pageNumber > 0 ? pageNumber - 1 : pageNumber);
  }
</script>

<PageHeader title={$t('results')} description={$t('resultListBody')}>
  {#snippet icon()}
    <LibraryBig class="size-5 text-muted-foreground" aria-hidden="true" />
  {/snippet}
</PageHeader>
<Card.Root>
  <Card.Header>
    <Card.Title>{$t('resultHistoryTitle')}</Card.Title>
    <Card.Description>{$t('resultHistoryBody')}</Card.Description>
  </Card.Header>
  <Card.Content>
    <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:justify-between">
      <label class="relative w-full sm:max-w-sm">
        <span class="sr-only">{$t('search')}</span>
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={17} aria-hidden="true" />
        <Input bind:value={search} oninput={scheduleSearch} placeholder={$t('search')} class="pl-9" />
      </label>
      <label>
        <span class="sr-only">{$t('status')}</span>
        <Select.Root type="single" value={status} onValueChange={changeStatus}>
          <Select.Trigger class="w-[180px]">
            {status === 'ALL' ? $t('allStatuses') : statusLabel(status, $locale)}
          </Select.Trigger>
          <Select.Content>
            <Select.Item value="ALL">{$t('allStatuses')}</Select.Item>
            <Select.Item value="SUCCEEDED">{statusLabel('SUCCEEDED', $locale)}</Select.Item>
            <Select.Item value="FAILED">{statusLabel('FAILED', $locale)}</Select.Item>
          </Select.Content>
        </Select.Root>
      </label>
    </div>
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
                            class="block h-auto max-w-full whitespace-normal break-words p-0 text-left"
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

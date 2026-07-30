<script lang="ts">
  import { onMount } from 'svelte';
  import { Search } from '@lucide/svelte';
  import { api, ApiError } from '$lib/api';
  import { locale, t } from '$lib/i18n';
  import type { Execution } from '$lib/types';
  import { formatDate, formatDuration } from '$lib/utils';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import * as Card from '$lib/components/ui/card/index.js';
  import { Input } from '$lib/components/ui/input/index.js';
  import * as Table from '$lib/components/ui/table/index.js';
  import * as Select from '$lib/components/ui/select/index.js';
  import * as Alert from '$lib/components/ui/alert/index.js';
  import StateView from '$lib/components/StateView.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import ServerPagination from '$lib/components/ServerPagination.svelte';
  import DeleteExecutionButton from '$lib/components/DeleteExecutionButton.svelte';

  let executions = $state<Execution[]>([]);
  let loading = $state(true);
  let error = $state('');
  let unsupported = $state(false);
  let search = $state('');
  let status = $state('ALL');
  let pageNumber = $state(0);
  let pageSize = $state(20);
  let totalElements = $state(0);
  let totalPages = $state(0);
  let searchTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(load);
  async function load(targetPage = pageNumber) {
    loading = true;
    error = '';
    unsupported = false;
    try {
      const response = await api.executionPage({
        page: targetPage, size: pageSize,
        statuses: status === 'ALL' ? [] : [status],
        search
      });
      executions = response.items;
      pageNumber = response.page;
      totalElements = response.totalElements;
      totalPages = response.totalPages;
    } catch (cause) {
      if (cause instanceof ApiError && [404, 405].includes(cause.status)) unsupported = true;
      else error = $t('apiUnavailable');
    } finally {
      loading = false;
    }
  }

  function scheduleSearch() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => void load(0), 300);
  }

  function changeStatus(value: string | undefined) {
    if (!value) return;
    status = value;
    void load(0);
  }

  function changeSize(value: number) {
    pageSize = value;
    void load(0);
  }

  async function afterDelete() {
    await load(executions.length === 1 && pageNumber > 0 ? pageNumber - 1 : pageNumber);
  }

  function terminal(value: string) {
    return ['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(value);
  }
</script>

<PageHeader title={$t('executionListTitle')} description={$t('executionListBody')} />
<Card.Root>
  <Card.Header>
    <Card.Title>{$t('executions')}</Card.Title>
    <Card.Description>{$t('executionListBody')}</Card.Description>
  </Card.Header>
  <Card.Content>
  <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:justify-between">
    <label class="relative w-full sm:max-w-sm">
      <span class="sr-only">{$t('search')}</span><Search class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={17} aria-hidden="true" />
      <Input bind:value={search} oninput={scheduleSearch} placeholder={$t('search')} class="pl-9" />
    </label>
    <label>
      <span class="sr-only">{$t('status')}</span>
      <Select.Root type="single" value={status} onValueChange={changeStatus}>
        <Select.Trigger class="w-[180px]">{status === 'ALL' ? $t('allStatuses') : status}</Select.Trigger>
        <Select.Content>
          <Select.Item value="ALL">{$t('allStatuses')}</Select.Item>
          <Select.Item value="QUEUED">QUEUED</Select.Item>
          <Select.Item value="RUNNING">RUNNING</Select.Item>
          <Select.Item value="TRAINING">TRAINING</Select.Item>
          <Select.Item value="SUCCEEDED">SUCCEEDED</Select.Item>
          <Select.Item value="FAILED">FAILED</Select.Item>
          <Select.Item value="CANCELLED">CANCELLED</Select.Item>
        </Select.Content>
      </Select.Root>
    </label>
  </div>
  {#if unsupported}
    <Alert.Root><Alert.Description>{$t('listNotSupported')}</Alert.Description></Alert.Root>
  {:else}
    <StateView loading={loading && executions.length === 0} {error} empty={!loading && !error && executions.length === 0} emptyText={$t('noExecutions')} onretry={load} />
  {/if}
  {#if executions.length}
    <div
      class="overflow-x-auto transition-opacity duration-150"
      class:opacity-60={loading}
      aria-busy={loading}
    >
      <Table.Root>
        <Table.Header><Table.Row><Table.Head>{$t('type')}</Table.Head><Table.Head>{$t('entity')}</Table.Head><Table.Head>{$t('requester')}</Table.Head><Table.Head>{$t('requestedAt')}</Table.Head><Table.Head>{$t('duration')}</Table.Head><Table.Head>{$t('status')}</Table.Head><Table.Head><span class="sr-only">{$t('delete')}</span></Table.Head></Table.Row></Table.Header>
        <Table.Body>
          {#each executions as item}
            <Table.Row>
              <Table.Cell><Button href={`/executions/${item.id}`} variant="link" class="h-auto p-0">{item.executionType.toUpperCase().includes('ML') ? $t('ml') : $t('report')}</Button></Table.Cell>
              <Table.Cell>{item.entityName ?? item.entityId}</Table.Cell>
              <Table.Cell>{item.requester ?? '—'}</Table.Cell>
              <Table.Cell>{formatDate(item.requestedAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}</Table.Cell>
              <Table.Cell>{formatDuration(item.startedAt, item.completedAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}</Table.Cell>
              <Table.Cell><StatusBadge status={item.status} /></Table.Cell>
              <Table.Cell class="text-right">
                {#if terminal(item.status)}
                  <DeleteExecutionButton
                    executionId={item.id}
                    compact
                    onDeleted={afterDelete}
                  />
                {/if}
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
    onPage={(value) => void load(value)}
    onSize={changeSize}
  />
  </Card.Content>
</Card.Root>

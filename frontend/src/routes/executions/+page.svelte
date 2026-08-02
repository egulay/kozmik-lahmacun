<script lang="ts">
  import { onMount } from 'svelte';
  import { Activity, ChevronDown, ChevronRight, LoaderCircle, Search } from '@lucide/svelte';
  import { api, ApiError } from '$lib/api';
  import { locale, statusLabel, t } from '$lib/i18n';
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
  import { Badge } from '$lib/components/ui/badge/index.js';
  import ServerPagination from '$lib/components/ServerPagination.svelte';
  import DeleteExecutionButton from '$lib/components/DeleteExecutionButton.svelte';
  import { openWorkspaceTab } from '$lib/workspace-tabs';
  import { DurableEventStream } from '$lib/sse';
  import ExecutionTypeIcon from '$lib/components/ExecutionTypeIcon.svelte';

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
  let refreshTimer: ReturnType<typeof setInterval> | undefined;
  let durationTimer: ReturnType<typeof setInterval> | undefined;
  let silentRefreshTimer: ReturnType<typeof setTimeout> | undefined;
  let durationNow = $state(Date.now());
  let expanded = $state<Set<string>>(new Set());
  let liveStages = $state<Record<string, string>>({});
  let liveProgress = $state<Record<string, number>>({});
  const streams = new Map<string, DurableEventStream>();

  onMount(() => {
    openWorkspaceTab({
      pageId: 'executions',
      title: $t('executions'),
      tabType: 'page'
    });
    void load();
    refreshTimer = setInterval(() => {
      void load(pageNumber, false);
      void refreshExpandedStages();
    }, 2_000);
    durationTimer = setInterval(() => (durationNow = Date.now()), 1_000);
    return () => {
      if (refreshTimer) clearInterval(refreshTimer);
      if (durationTimer) clearInterval(durationTimer);
      if (silentRefreshTimer) clearTimeout(silentRefreshTimer);
      streams.forEach((stream) => stream.close());
      streams.clear();
    };
  });
  async function load(targetPage = pageNumber, showLoading = true) {
    if (showLoading) loading = true;
    error = '';
    unsupported = false;
    try {
      const response = await api.executionPage({
        page: targetPage, size: pageSize,
        statuses: status === 'ALL' ? [] : [status],
        search
      });
      executions = response.items;
      for (const item of response.items) {
        if (item.latestStage) {
          updateLiveStage(item.id, item.latestStage, item.latestProgressPercent ?? 0);
        }
      }
      pageNumber = response.page;
      totalElements = response.totalElements;
      totalPages = response.totalPages;
      syncStreams(response.items);
    } catch (cause) {
      if (cause instanceof ApiError && [404, 405].includes(cause.status)) unsupported = true;
      else error = $t('apiUnavailable');
    } finally {
      if (showLoading) loading = false;
    }
  }

  function syncStreams(items: Execution[]) {
    const activeIds = new Set(items.filter((item) => !terminal(item.status)).map((item) => item.id));
    for (const [id, stream] of streams) {
      if (!activeIds.has(id)) {
        stream.close();
        streams.delete(id);
      }
    }
    for (const id of activeIds) {
      if (streams.has(id)) continue;
      void loadLiveStage(id);
      const stream = new DurableEventStream(`/api/executions/${id}/stream`, {
        onReconnect: () => scheduleSilentRefresh(),
        onEvent: (event, name) => {
          if (name === 'heartbeat') return;
          try {
            const payload = JSON.parse(event.data) as {
              stage?: unknown;
              progressPercent?: unknown;
            };
            if (typeof payload.stage === 'string') {
              updateLiveStage(
                id,
                payload.stage,
                typeof payload.progressPercent === 'number' ? payload.progressPercent : 0
              );
            }
          } catch {
            // Authoritative REST reload below handles malformed or non-status events.
          }
          void loadLiveStage(id);
          scheduleSilentRefresh();
        }
      });
      streams.set(id, stream);
      stream.connect();
    }
  }

  async function loadLiveStage(executionId: string) {
    try {
      const state = await api.execution(executionId);
      const latest = state.history?.at(-1);
      if (latest?.stage && executions.some((item) => item.id === executionId)) {
        updateLiveStage(executionId, latest.stage, latest.progressPercent);
      }
    } catch {
      // The list remains authoritative and the SSE reconnect path will retry.
    }
  }

  async function refreshExpandedStages() {
    const activeExpandedIds = executions
      .filter((item) => expanded.has(item.id) && !terminal(item.status))
      .map((item) => item.id);
    await Promise.all(activeExpandedIds.map((id) => loadLiveStage(id)));
  }

  function updateLiveStage(executionId: string, stage: string, progress: number) {
    const currentStage = liveStages[executionId];
    const currentProgress = liveProgress[executionId] ?? -1;
    const stageOrder = [
      'PLANNING', 'VALIDATING', 'VALIDATED', 'QUEUED', 'PREPARING',
      'RESOLVING_DATA', 'RUNNING', 'TRAINING', 'TUNING',
      'WRITING_RESULTS', 'SUMMARIZING', 'CANCELLATION_REQUESTED',
      'CANCELLED', 'TIMED_OUT', 'FAILED', 'COMPLETED'
    ];
    const currentOrder = currentStage ? stageOrder.indexOf(currentStage) : -1;
    const nextOrder = stageOrder.indexOf(stage);
    if (
      progress < currentProgress
      || (progress === currentProgress && nextOrder >= 0 && nextOrder < currentOrder)
    ) return;
    liveStages = { ...liveStages, [executionId]: stage };
    liveProgress = { ...liveProgress, [executionId]: progress };
  }

  function scheduleSilentRefresh() {
    if (silentRefreshTimer) clearTimeout(silentRefreshTimer);
    silentRefreshTimer = setTimeout(() => void load(pageNumber, false), 100);
  }

  function toggleExpanded(id: string) {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id);
    else {
      next.add(id);
      void loadLiveStage(id);
    }
    expanded = next;
  }

  function resultNavigable(item: Execution) {
    return ['SUCCEEDED', 'FAILED'].includes(item.status);
  }

  function parentStatus(item: Execution) {
    return terminal(item.status) ? item.status : 'RUNNING';
  }

  function liveStage(item: Execution) {
    if (item.status === 'SUCCEEDED') return 'COMPLETED';
    if (terminal(item.status)) return item.status;
    return liveStages[item.id] ?? item.status;
  }

  function stageLabel(stage: string) {
    if (stage === 'PLANNING') return $t('timelineStagePlanning');
    if (stage === 'VALIDATING' || stage === 'VALIDATED') return $t('timelineStageValidating');
    if (stage === 'QUEUED') return $t('timelineStageQueued');
    if (stage === 'PREPARING') return $t('timelineStagePreparing');
    if (stage === 'RESOLVING_DATA') return $t('resolvingData');
    if (stage === 'TUNING') return $t('tuningModels');
    if (stage === 'TRAINING') return $t('timelineStageTraining');
    if (stage === 'RUNNING') return $t('timelineStageRunning');
    if (stage === 'WRITING_RESULTS') return $t('timelineStageWritingResults');
    if (stage === 'SUMMARIZING') return $t('timelineStageSummarizing');
    if (stage === 'COMPLETED') return $t('timelineStageCompleted');
    if (stage === 'FAILED') return $t('timelineStageFailed');
    if (stage === 'CANCELLED') return $t('timelineStageCancelled');
    if (stage === 'TIMED_OUT') return $t('timelineStageTimedOut');
    if (stage === 'CANCELLATION_REQUESTED') return $t('timelineStageCancellationRequested');
    return statusLabel(stage, $locale);
  }

  function entityLabel(item: Execution) {
    return $locale === 'tr'
      ? item.entityNameTr || item.entityName || item.entityId
      : item.entityName || item.entityId;
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

<PageHeader title={$t('executionListTitle')} description={$t('executionListBody')}>
  {#snippet icon()}
    <Activity class="size-5 text-muted-foreground" aria-hidden="true" />
  {/snippet}
</PageHeader>
<Card.Root>
  <Card.Header>
    <Card.Title>{$t('executionHistoryTitle')}</Card.Title>
    <Card.Description>{$t('executionHistoryBody')}</Card.Description>
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
        <Select.Trigger class="w-[180px]">{status === 'ALL' ? $t('allStatuses') : statusLabel(status, $locale)}</Select.Trigger>
        <Select.Content>
          <Select.Item value="ALL">{$t('allStatuses')}</Select.Item>
          {#each ['PLANNING', 'VALIDATED', 'QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'] as option}
            <Select.Item value={option}>{statusLabel(option, $locale)}</Select.Item>
          {/each}
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
        <Table.Header><Table.Row><Table.Head>{$t('type')}</Table.Head><Table.Head>{$t('entity')}</Table.Head><Table.Head>{$t('requester')}</Table.Head><Table.Head>{$t('requestedAt')}</Table.Head><Table.Head class="w-44 min-w-44">{$t('duration')}</Table.Head><Table.Head>{$t('status')}</Table.Head><Table.Head><span class="sr-only">{$t('delete')}</span></Table.Head></Table.Row></Table.Header>
        <Table.Body>
          {#each executions as item (item.id)}
            <Table.Row
              class="cursor-pointer"
              tabindex={0}
              aria-expanded={expanded.has(item.id)}
              onclick={() => toggleExpanded(item.id)}
              onkeydown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  toggleExpanded(item.id);
                }
              }}
            >
              <Table.Cell>
                <span class="flex items-center gap-2">
                  {#if expanded.has(item.id)}<ChevronDown size={16} />{:else}<ChevronRight size={16} />{/if}
                  <Button
                    href={`/executions/${item.id}`}
                    variant="link"
                    class="h-auto p-0"
                    onclick={(event) => event.stopPropagation()}
                  >{item.executionType.toUpperCase().includes('ML') ? $t('ml') : $t('report')}</Button>
                </span>
              </Table.Cell>
              <Table.Cell>{entityLabel(item)}</Table.Cell>
              <Table.Cell>{item.requester ?? '—'}</Table.Cell>
              <Table.Cell>{formatDate(item.requestedAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}</Table.Cell>
              <Table.Cell class="w-44 min-w-44 whitespace-nowrap tabular-nums">{formatDuration(
                item.requestedAt,
                item.completedAt ?? new Date(durationNow).toISOString(),
                $locale === 'tr' ? 'tr-TR' : 'en-US'
              )}</Table.Cell>
              <Table.Cell><StatusBadge status={parentStatus(item)} /></Table.Cell>
              <Table.Cell class="text-right">
                {#if terminal(item.status)}
                  <span onclick={(event) => event.stopPropagation()} role="presentation">
                    <DeleteExecutionButton
                      executionId={item.id}
                      compact
                      onDeleted={afterDelete}
                    />
                  </span>
                {/if}
              </Table.Cell>
            </Table.Row>
            {#if expanded.has(item.id)}
              <Table.Row class="bg-muted/25 hover:bg-muted/25">
                <Table.Cell colspan={7} class="py-3 pl-12">
                  <div class="flex items-center gap-3 border-l-2 border-border pl-4">
                    {#if resultNavigable(item)}
                      <ExecutionTypeIcon
                        kind={item.executionType}
                        status={item.status}
                        context="result"
                      />
                      <div class="min-w-0 flex-1">
                        <p class="text-xs text-muted-foreground">{$t('resultAvailable')}</p>
                        <Button href={`/results/${item.id}`} variant="link" class="h-auto max-w-full whitespace-normal break-words p-0 text-left">
                          {item.originalRequest ?? item.id}
                        </Button>
                      </div>
                    {:else if terminal(item.status)}
                      <ExecutionTypeIcon
                        kind={item.executionType}
                        status={item.status}
                        context="result"
                      />
                      <p class="text-sm text-muted-foreground">{$t('resultUnavailable')}</p>
                    {:else}
                      <LoaderCircle class="size-4 shrink-0 animate-spin text-muted-foreground" />
                      <p class="flex-1 text-sm text-muted-foreground">{$t('resultStillWorking')}</p>
                    {/if}
                    <Badge variant="secondary" class="shrink-0 uppercase">
                      {stageLabel(liveStage(item))}
                    </Badge>
                  </div>
                </Table.Cell>
              </Table.Row>
            {/if}
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

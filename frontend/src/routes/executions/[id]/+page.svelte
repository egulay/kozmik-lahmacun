<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  import { tick } from 'svelte';
  import { ArrowLeft, Ban, ChartNoAxesCombined, LoaderCircle, SquareTerminal, TriangleAlert, X } from '@lucide/svelte';
  import { api } from '$lib/api';
  import { locale, t } from '$lib/i18n';
  import type { EntitySummary, Execution } from '$lib/types';
  import { subscribeExecutionEvents } from '$lib/execution-events';
  import { formatDate, formatDuration } from '$lib/utils';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Card from '$lib/components/ui/card/index.js';
  import * as Alert from '$lib/components/ui/alert/index.js';
  import * as Dialog from '$lib/components/ui/dialog/index.js';
  import * as Sheet from '$lib/components/ui/sheet/index.js';
  import { Badge } from '$lib/components/ui/badge/index.js';
  import { Separator } from '$lib/components/ui/separator/index.js';
  import { Progress } from '$lib/components/ui/progress/index.js';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import StateView from '$lib/components/StateView.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import JsonDisplay from '$lib/components/JsonDisplay.svelte';
  import {
    closeExecutionWorkspace,
    deleteWorkspaceView,
    getWorkspaceView,
    openWorkspaceTab,
    setWorkspaceView
  } from '$lib/workspace-tabs';
  import DeleteExecutionButton from '$lib/components/DeleteExecutionButton.svelte';
  import PdfExportButton from '$lib/components/PdfExportButton.svelte';
  import ProgressStageIcon from '$lib/components/ProgressStageIcon.svelte';
  import MarkdownMessage from '$lib/components/MarkdownMessage.svelte';
  import ExecutionTypeIcon from '$lib/components/ExecutionTypeIcon.svelte';
  import { lifecycleTimeline } from '$lib/execution-timeline';

  type ExecutionView = { execution: Execution; localizedEntity: EntitySummary | null };
  const initialView = getWorkspaceView<ExecutionView>(`execution:${$page.params.id}:${$locale}`);
  let execution = $state<Execution | null>(initialView?.execution ?? null);
  let localizedEntity = $state<EntitySummary | null>(initialView?.localizedEntity ?? null);
  let loading = $state(!initialView);
  let error = $state('');
  let cancelling = $state(false);
  let unsubscribeExecutionEvents: (() => void) | undefined;
  let durationTimer: ReturnType<typeof setInterval> | undefined;
  let durationNow = $state(Date.now());
  let cancelDialogOpen = $state(false);
  let sparkConsoleElement = $state<HTMLDivElement>();
  let sparkConsoleFollowLatest = $state(true);
  let sparkConsoleOpen = $state(false);
  const terminalStatuses = new Set(['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT']);

  function isTerminal(status: string): boolean {
    return terminalStatuses.has(status);
  }

  function applyExecution(loadedExecution: Execution): boolean {
    if (
      execution?.id === loadedExecution.id
      && isTerminal(execution.status)
      && !isTerminal(loadedExecution.status)
    ) {
      return false;
    }
    execution = loadedExecution;
    return true;
  }

  $effect(() => {
    const executionId = $page.params.id;
    const selectedLocale = $locale;
    if (!executionId) return;

    void load(executionId, selectedLocale);
  });

  onMount(() => {
    unsubscribeExecutionEvents = subscribeExecutionEvents((event, name) => {
      if (name === 'heartbeat') return;
      if (name === 'reconnect') {
        void refresh();
        return;
      }
      try {
        const payload = JSON.parse(event.data) as { executionId?: unknown };
        if (payload.executionId === $page.params.id) void refresh();
      } catch {
        // Authoritative reload remains available after the next valid event.
      }
    });
    durationTimer = setInterval(() => {
      durationNow = Date.now();
    }, 1_000);
    return () => {
      unsubscribeExecutionEvents?.();
      if (durationTimer) clearInterval(durationTimer);
    };
  });

  async function load(executionId = $page.params.id!, selectedLocale = $locale) {
    const initialLoad = execution?.id !== executionId;
    if (initialLoad) {
      loading = true;
      sparkConsoleFollowLatest = true;
    }
    try {
      const loadedExecution = await api.execution(executionId);
      const loadedEntity = await api.entity(loadedExecution.entityId).catch(() => null);
      if ($page.params.id !== executionId || $locale !== selectedLocale) return;
      if (!applyExecution(loadedExecution)) return;
      localizedEntity = loadedEntity;
      setWorkspaceView<ExecutionView>(`execution:${executionId}:${selectedLocale}`, {
        execution: loadedExecution,
        localizedEntity: loadedEntity
      });
      openWorkspaceTab({
        executionId: loadedExecution.id,
        title: loadedExecution.originalRequest?.slice(0, 48)
          || `${loadedExecution.executionType} · ${loadedExecution.id.slice(0, 8)}`,
        kind: loadedExecution.executionType.toUpperCase().includes('ML') ? 'ML' : 'REPORT',
        status: loadedExecution.status,
        tabType: 'execution'
      });
      error = '';
    } catch {
      if ($page.params.id !== executionId || $locale !== selectedLocale) return;
      error = $t('apiUnavailable');
    } finally {
      if (
        initialLoad
        && $page.params.id === executionId
        && $locale === selectedLocale
      ) loading = false;
    }
  }

  async function refresh() {
    if (!execution || isTerminal(execution.status)) {
      return;
    }
    try {
      const executionId = $page.params.id!;
      const loadedExecution = await api.execution(executionId);
      if ($page.params.id !== executionId) return;
      applyExecution(loadedExecution);
    } catch { /* Keep the last durable state until reconnect. */ }
  }

  async function cancel() {
    const executionId = execution?.id;
    cancelDialogOpen = false;
    if (!executionId) return;
    cancelling = true;
    try {
      await api.cancelExecution(executionId);
      if ($page.params.id === executionId) {
        await load(executionId);
      }
    } catch {
      error = $t('featureUnavailable');
    } finally {
      cancelling = false;
    }
  }

  function stageLabel(stage: string) {
    let label = stage.replaceAll('_', ' ');
    if (stage === 'PLANNING') label = $t('timelineStagePlanning');
    if (stage === 'VALIDATING') label = $t('timelineStageValidating');
    if (stage === 'QUEUED') label = $t('timelineStageQueued');
    if (stage === 'PREPARING') label = $t('timelineStagePreparing');
    if (stage === 'RESOLVING_DATA') label = $t('resolvingData');
    if (stage === 'TUNING') label = $t('tuningModels');
    if (stage === 'TRAINING') label = $t('timelineStageTraining');
    if (stage === 'RUNNING') label = $t('timelineStageRunning');
    if (stage === 'WRITING_RESULTS') label = $t('timelineStageWritingResults');
    if (stage === 'SUMMARIZING') label = $t('timelineStageSummarizing');
    if (stage === 'COMPLETED') label = $t('timelineStageCompleted');
    if (stage === 'FAILED') label = $t('timelineStageFailed');
    if (stage === 'CANCELLED') label = $t('timelineStageCancelled');
    if (stage === 'TIMED_OUT') label = $t('timelineStageTimedOut');
    if (stage === 'CANCELLATION_REQUESTED') {
      label = $t('timelineStageCancellationRequested');
    }
    return label.toLocaleUpperCase($locale === 'tr' ? 'tr-TR' : 'en-US');
  }

  function messageLabel(code: string) {
    return code;
  }

  const failureExplanation = $derived.by(() => {
    if (execution?.status !== 'FAILED') return '';
    if (execution.failure?.userExplanation) return execution.failure.userExplanation;
    if (execution.history.at(-1)?.stage === 'PLANNING') {
      return $t('planningFailed');
    }
    const payload = execution.order?.payload;
    if (payload && typeof payload === 'object') {
      const report = payload as Record<string, unknown>;
      const aggregations = Array.isArray(report.aggregations) ? report.aggregations : [];
      const groupBy = Array.isArray(report.groupBy) ? report.groupBy : [];
      const selections = Array.isArray(report.select) ? report.select : [];
      if (aggregations.length && !groupBy.length && selections.length) {
        return $t('mixedReportFailure');
      }
    }
    return $t('sparkJobFailed');
  });

  const hasApprovedOrder = $derived.by(() =>
    Boolean(execution?.order && Object.keys(execution.order).length > 0)
  );

  const orderLabel = $derived.by(() => {
    if (!execution?.order) return '—';
    const algorithm = execution.order.algorithm;
    if (typeof algorithm === 'string') return algorithm;
    const aggregations = execution.order.aggregations;
    if (Array.isArray(aggregations)) return aggregations.map(String).join(', ');
    return execution.executionType.toUpperCase().includes('ML') ? $t('ml') : $t('report');
  });

  const currentProgress = $derived.by(() => {
    if (!execution) return 0;
    if (execution.status === 'SUCCEEDED') return 100;
    return Math.max(
      0,
      Math.min(100, execution.history.at(-1)?.progressPercent ?? 0)
    );
  });

  const timelineHistory = $derived.by(() => {
    if (!execution) return [];
    return lifecycleTimeline(execution.history, execution.executionType);
  });

  const sparkConsoleHistory = $derived.by(() =>
    execution
      ? execution.history.filter((item) => [
          'EXECUTION_SPARK_RUNNING', 'EXECUTION_ML_TRAINING',
          'EXECUTION_ML_TUNING', 'EXECUTION_SPARK_PROGRESS',
          'EXECUTION_WRITING_RESULTS', 'SPARK_JOB_FAILED',
          'SPARK_RUNTIME_UNAVAILABLE'
        ].includes(item.messageCode))
      : []
  );

  $effect(() => {
    const entryCount = sparkConsoleHistory.length;
    if (!entryCount || !sparkConsoleElement || !sparkConsoleFollowLatest) return;
    void tick().then(() => {
      if (sparkConsoleElement) {
        sparkConsoleElement.scrollTop = sparkConsoleElement.scrollHeight;
      }
    });
  });

  function handleSparkConsoleScroll() {
    if (!sparkConsoleElement) return;
    const distanceFromBottom = sparkConsoleElement.scrollHeight
      - sparkConsoleElement.scrollTop - sparkConsoleElement.clientHeight;
    sparkConsoleFollowLatest = distanceFromBottom <= 12;
  }

  function followLatestSparkOutput() {
    sparkConsoleFollowLatest = true;
    void tick().then(() => {
      if (sparkConsoleElement) {
        sparkConsoleElement.scrollTop = sparkConsoleElement.scrollHeight;
      }
    });
  }

  function numericDetail(item: { details?: unknown }, key: string): number {
    if (!item.details || typeof item.details !== 'object') return 0;
    const value = (item.details as Record<string, unknown>)[key];
    return typeof value === 'number' ? value : 0;
  }

  function consoleMessage(item: Execution['history'][number]): string {
    if (item.messageCode === 'EXECUTION_SPARK_PROGRESS') {
      return $t('sparkProgressMessage')
        .replace('{jobs}', String(numericDetail(item, 'jobCount')))
        .replace('{stages}', String(numericDetail(item, 'stageCount')))
        .replace('{completed}', String(numericDetail(item, 'completedTasks')))
        .replace('{total}', String(numericDetail(item, 'totalTasks')))
        .replace('{active}', String(numericDetail(item, 'activeTasks')))
        .replace('{failed}', String(numericDetail(item, 'failedTasks')));
    }
    if (item.messageCode === 'EXECUTION_ML_TUNING') return $t('sparkTuningStarted');
    if (item.messageCode === 'EXECUTION_ML_TRAINING') return $t('sparkTrainingStarted');
    if (item.messageCode === 'EXECUTION_WRITING_RESULTS') return $t('sparkResultWriting');
    if (item.messageCode === 'SPARK_JOB_FAILED') return $t('sparkConsoleFailed');
    if (item.messageCode === 'SPARK_RUNTIME_UNAVAILABLE') return $t('sparkRuntimeUnavailable');
    return $t('sparkExecutionStarted');
  }

  async function afterDelete() {
    if (!execution) return;
    deleteWorkspaceView(`execution:${execution.id}:en`);
    deleteWorkspaceView(`execution:${execution.id}:tr`);
    closeExecutionWorkspace(execution.id);
    await goto('/executions');
  }
</script>

<div class="pdf-brand"><strong>{$t('brand')}</strong><span>{$t('governedAnalytics')}</span></div>
<PageHeader
  title={execution
    ? (execution.executionType.toUpperCase().includes('ML') ? $t('ml') : $t('report'))
    : $t('details')}
  description={execution?.id}
  sticky
>
  {#snippet icon()}
    {#if execution && !isTerminal(execution.status)}
      <LoaderCircle class="size-5 animate-spin text-muted-foreground" aria-hidden="true" />
    {:else if execution}
      <ExecutionTypeIcon
        kind={execution.executionType}
        status={execution.status}
        context="execution"
        class="size-5 text-muted-foreground"
      />
    {/if}
  {/snippet}
  {#snippet actions()}
    <div class="flex flex-wrap justify-end gap-2">
      {#if execution?.status === 'SUCCEEDED'}
        <Button href={`/results/${execution.id}`} size="sm"><ChartNoAxesCombined size={16} />{$t('viewResult')}</Button>
      {/if}
      {#if execution && isTerminal(execution.status)}
        <PdfExportButton documentId={execution.id} documentType="execution" />
      {/if}
      {#if execution && isTerminal(execution.status)}
        <DeleteExecutionButton executionId={execution.id} onDeleted={afterDelete} />
      {/if}
      <Button href="/executions" variant="outline" size="sm"><ArrowLeft size={16} />{$t('back')}</Button>
    </div>
  {/snippet}
</PageHeader>
<div class="pdf-document">
<StateView loading={loading && !execution} {error} onretry={load} />
{#if execution}
  {#if failureExplanation}
    <Alert.Root variant="destructive" class="mb-4">
      <TriangleAlert />
      <Alert.Title>{$t('failureReason')}</Alert.Title>
      <Alert.Description class="space-y-3 leading-relaxed">
        <MarkdownMessage content={failureExplanation} />
        {#if execution.failure}
          <div class="rounded-md border border-destructive/30 bg-background/60 p-3 text-foreground">
            <strong class="text-sm">{$t('sanitizedReason')}</strong>
            <p class="mt-1 text-sm text-muted-foreground">
              {execution.failure.sanitizedTechnicalReason}
            </p>
            {#if execution.failure.explanationStatus === 'FAILED'}
              <p class="mt-2 text-xs text-muted-foreground">{$t('explanationFallback')}</p>
            {/if}
          </div>
        {/if}
      </Alert.Description>
    </Alert.Root>
  {/if}
  <div class="mb-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
    <Card.Root><Card.Header><Card.Description>{$t('status')}</Card.Description><Card.Title><StatusBadge status={execution.status} /></Card.Title></Card.Header></Card.Root>
    <Card.Root><Card.Header><Card.Description>{$t('entity')}</Card.Description><Card.Title class="truncate text-base">{localizedEntity?.name ?? execution.entityName ?? execution.entityId}</Card.Title></Card.Header></Card.Root>
    <Card.Root><Card.Header><Card.Description>{$t('requestedAt')}</Card.Description><Card.Title class="text-base">{formatDate(execution.requestedAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}</Card.Title></Card.Header></Card.Root>
    <Card.Root><Card.Header><Card.Description>{$t('duration')}</Card.Description><Card.Title class="text-base">{formatDuration(
      execution.requestedAt,
      execution.completedAt ?? new Date(durationNow).toISOString(),
      $locale === 'tr' ? 'tr-TR' : 'en-US'
    )}</Card.Title></Card.Header></Card.Root>
    <Card.Root>
      <Card.Header><Card.Description>{$t('plan')}</Card.Description><Card.Title class="truncate text-base">{orderLabel}</Card.Title></Card.Header>
      <Card.Content>
        <Dialog.Root>
          <Dialog.Trigger>{#snippet child({ props })}<Button {...props} variant="outline" size="sm">{$t('technicalDetails')}</Button>{/snippet}</Dialog.Trigger>
          <Dialog.Content class="max-w-2xl">
            <Dialog.Header>
              <Dialog.Title>{$t('technicalDetails')}</Dialog.Title>
              <Dialog.Description>
                {execution.executionType === 'ML' ? $t('approvedMlOrder') : $t('approvedReportPlan')}
              </Dialog.Description>
            </Dialog.Header>
            {#if hasApprovedOrder}
              <JsonDisplay
                value={execution.order}
                copyLabel={$t('copyJson')}
                copiedLabel={$t('copied')}
              />
            {:else}
              <Alert.Root variant={execution.status === 'FAILED' ? 'destructive' : 'default'}>
                <TriangleAlert />
                <Alert.Title>{execution.status === 'FAILED' ? $t('orderUnavailable') : $t('orderPending')}</Alert.Title>
                <Alert.Description>
                  {execution.status === 'FAILED' ? $t('orderUnavailableBody') : $t('orderPendingBody')}
                </Alert.Description>
              </Alert.Root>
            {/if}
          </Dialog.Content>
        </Dialog.Root>
      </Card.Content>
    </Card.Root>
  </div>
  <Card.Root class="mb-4">
    <Card.Header><Card.Title>{$t('originalRequest')}</Card.Title></Card.Header>
    <Card.Content class="text-sm leading-relaxed text-muted-foreground">{execution.originalRequest ?? String(execution.order?.request ?? '—')}</Card.Content>
  </Card.Root>
  <Card.Root class="pdf-breakable pdf-exclude">
    <Card.Header class="flex flex-row items-start justify-between">
      <div class="min-w-0 flex-1"><Card.Title>{$t('timeline')}</Card.Title><Card.Description>{timelineHistory.length} {$t('status')}</Card.Description></div>
      <div class="ml-auto flex shrink-0 items-center gap-2">
        <Button variant="outline" size="sm" onclick={() => (sparkConsoleOpen = true)}>
          <SquareTerminal size={15} />
          <span class="relative">
            {$t('liveConsoleButton')}
            {#if !['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(execution.status)}
              <span class="absolute -right-2 -top-1 size-1.5 animate-pulse rounded-full bg-emerald-500" aria-hidden="true"></span>
            {/if}
          </span>
        </Button>
        {#if !['SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT'].includes(execution.status)}
          <Button variant="outline" size="sm" disabled={cancelling} onclick={() => (cancelDialogOpen = true)}><Ban size={15} />{$t('cancel')}</Button>
        {/if}
      </div>
    </Card.Header>
    <Card.Content>
      <div class="mb-4 space-y-2" aria-live="polite">
        <div class="flex items-center justify-between text-sm">
          <span class="font-medium">{$t('progress')}</span>
          <span class="tabular-nums text-muted-foreground">{currentProgress}%</span>
        </div>
        <Progress value={currentProgress} aria-label={`${$t('progress')} ${currentProgress}%`} />
      </div>
      <ol class="grid gap-0">
      {#each timelineHistory as item}
        <li class="grid grid-cols-[auto_1fr_auto] gap-3 py-3">
          <ProgressStageIcon stage={item.stage} />
          <div><strong class="text-sm">{stageLabel(item.stage)}</strong><small class="block text-xs text-muted-foreground">{formatDate(item.occurredAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}</small><p class="mt-1 text-sm text-muted-foreground">{messageLabel(item.messageCode)}</p></div>
          <Badge variant="secondary">{item.progressPercent}%</Badge>
        </li>
        <Separator />
      {/each}
      </ol>
    </Card.Content>
  </Card.Root>
  {#if execution.status === 'SUCCEEDED'}
    <Card.Root class="pdf-exclude mt-4"><Card.Header class="flex-row items-center gap-3"><ChartNoAxesCombined size={24} /><div class="flex-1"><Card.Title>{$t('resultReady')}</Card.Title><Card.Description>{$t('artifactGuidance')}</Card.Description></div><Button href={`/results/${execution.id}`}>{$t('viewResult')}</Button></Card.Header></Card.Root>
  {/if}
{/if}

<Dialog.Root bind:open={cancelDialogOpen}>
  <Dialog.Content>
    <Dialog.Header><Dialog.Title>{$t('cancel')}</Dialog.Title><Dialog.Description>{$t('cancelConfirm')}</Dialog.Description></Dialog.Header>
    <Dialog.Footer><Dialog.Close>{#snippet child({ props })}<Button {...props} variant="outline">{$t('back')}</Button>{/snippet}</Dialog.Close><Button variant="destructive" disabled={cancelling} onclick={cancel}><Ban />{$t('cancel')}</Button></Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

<Sheet.Root bind:open={sparkConsoleOpen}>
  <Sheet.Content
    side="bottom"
    showCloseButton={false}
    class="mx-auto !h-[min(24rem,42dvh)] w-[calc(100%_-_1rem)] max-w-5xl gap-3 rounded-t-xl border-x sm:w-[calc(100%_-_2rem)]"
  >
    <Sheet.Header class="border-b px-4 pb-3 sm:px-6">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div class="min-w-0">
          <Sheet.Title class="flex items-center gap-2"><SquareTerminal size={18} />{$t('liveExecutionConsole')}</Sheet.Title>
          <Sheet.Description class="flex flex-wrap items-center gap-x-2">
            <span>{$t('liveExecutionConsoleBody')}</span>
            <span class="tabular-nums">· {sparkConsoleHistory.length} {$t('status')}</span>
          </Sheet.Description>
        </div>
        <div class="flex shrink-0 items-center gap-2 self-end sm:self-start">
          <Button
            variant={sparkConsoleFollowLatest ? 'secondary' : 'outline'}
            size="sm"
            onclick={followLatestSparkOutput}
          >{$t('followLatest')}</Button>
          <Sheet.Close>
            {#snippet child({ props })}
              <Button {...props} variant="outline" size="sm"><X size={15} />{$t('close')}</Button>
            {/snippet}
          </Sheet.Close>
        </div>
      </div>
      {#if execution}
        <div class="mt-2 flex min-w-0 items-center justify-between gap-4 text-xs">
          <div class="flex min-w-0 items-center gap-2">
            <span class="shrink-0 text-muted-foreground">{$t('executionId')}</span>
            <code class="truncate font-mono text-foreground" title={execution.id}>{execution.id}</code>
            <span class="shrink-0 text-border" aria-hidden="true">·</span>
            <span class="shrink-0 text-muted-foreground">{$t('duration')}</span>
            <span class="shrink-0 tabular-nums text-foreground">{formatDuration(
              execution.requestedAt,
              execution.completedAt ?? new Date(durationNow).toISOString(),
              $locale === 'tr' ? 'tr-TR' : 'en-US'
            )}</span>
          </div>
          <Badge class="shrink-0" variant="secondary">
            {execution.executionType.toUpperCase().includes('ML') ? $t('ml') : $t('report')}
          </Badge>
        </div>
      {/if}
    </Sheet.Header>
    <div class="min-h-0 flex-1 px-4 pb-4 sm:px-6">
      <div
        bind:this={sparkConsoleElement}
        onscroll={handleSparkConsoleScroll}
        class="h-full overflow-y-auto rounded-md border bg-zinc-950 p-3 font-mono text-xs text-zinc-100"
        aria-live="polite"
      >
        {#if sparkConsoleHistory.length}
          {#each sparkConsoleHistory as item}
            <div class="grid grid-cols-[auto_1fr] gap-3 py-1">
              <time class="whitespace-nowrap text-zinc-500">{new Date(item.occurredAt).toLocaleTimeString(
                $locale === 'tr' ? 'tr-TR' : 'en-GB',
                { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }
              )}</time>
              <span class:item-console-error={item.status === 'FAILED'}>{consoleMessage(item)}</span>
            </div>
          {/each}
        {:else}
          <p class="text-zinc-500">{$t('sparkConsoleWaiting')}</p>
        {/if}
      </div>
    </div>
  </Sheet.Content>
</Sheet.Root>
</div>

<style>
  .item-console-error { color: rgb(248 113 113); }
</style>

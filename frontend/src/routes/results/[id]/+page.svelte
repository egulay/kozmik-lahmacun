<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { ArrowLeft, Box, BrainCircuit, ClipboardList, Gauge, Info, TriangleAlert } from '@lucide/svelte';
  import type { EChartsOption } from 'echarts';
  import { api } from '$lib/api';
  import { locale, t } from '$lib/i18n';
  import type { ColumnDefinition, EntitySummary, ExecutionResult } from '$lib/types';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Card from '$lib/components/ui/card/index.js';
  import * as Table from '$lib/components/ui/table/index.js';
  import * as Alert from '$lib/components/ui/alert/index.js';
  import * as Dialog from '$lib/components/ui/dialog/index.js';
  import { Badge } from '$lib/components/ui/badge/index.js';
  import { Separator } from '$lib/components/ui/separator/index.js';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import StateView from '$lib/components/StateView.svelte';
  import ChartView from '$lib/components/ChartView.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import JsonDisplay from '$lib/components/JsonDisplay.svelte';
  import { closeExecutionWorkspace, openWorkspaceTab } from '$lib/workspace-tabs';
  import DeleteExecutionButton from '$lib/components/DeleteExecutionButton.svelte';
  import PdfExportButton from '$lib/components/PdfExportButton.svelte';
  import ServerPagination from '$lib/components/ServerPagination.svelte';
  import type { Execution } from '$lib/types';
  import {
    formatDate,
    formatDisplayValue,
    formatManagementSummary,
    formatTemporalBucket,
    humanizeField
  } from '$lib/utils';

  let result = $state<ExecutionResult | null>(null);
  let previewData = $state<unknown>(null);
  let previewPage = $state(0);
  let previewSize = $state(20);
  let previewTotalElements = $state(0);
  let previewTotalPages = $state(0);
  let execution = $state<Execution | null>(null);
  let localizedEntity = $state<EntitySummary | null>(null);
  let localizedColumns = $state<ColumnDefinition[]>([]);
  let loading = $state(true);
  let previewLoading = $state(false);
  let error = $state('');
  let loadSequence = 0;

  $effect(() => {
    const executionId = $page.params.id;
    const selectedLocale = $locale;
    if (executionId) void load(executionId, selectedLocale);
  });

  async function load(executionId: string, _selectedLocale = $locale) {
    const sequence = ++loadSequence;
    loading = true;
    error = '';
    try {
      const loadedExecution = await api.execution(executionId);
      const loadedResult = loadedExecution.status === 'SUCCEEDED'
        ? await api.result(executionId)
        : null;
      const [loadedEntity, loadedSchema] = await Promise.all([
        api.entity(loadedExecution.entityId).catch(() => null),
        api.entitySchema(loadedExecution.entityId).catch(() => null)
      ]);
      if (sequence !== loadSequence || $page.params.id !== executionId) return;
      result = loadedResult;
      previewData = loadedResult?.preview ?? null;
      previewPage = loadedResult?.previewPage ?? 0;
      previewSize = loadedResult?.previewSize ?? 20;
      previewTotalElements = loadedResult?.previewTotalElements ?? 0;
      previewTotalPages = loadedResult?.previewTotalPages ?? 0;
      execution = loadedExecution;
      localizedEntity = loadedEntity;
      localizedColumns = loadedSchema?.columns ?? [];
      openWorkspaceTab({
        executionId: loadedExecution.id,
        title: loadedExecution.originalRequest?.slice(0, 48)
          || `${loadedExecution.executionType} · ${loadedExecution.id.slice(0, 8)}`,
        kind: loadedExecution.executionType.toUpperCase().includes('ML') ? 'ML' : 'REPORT',
        status: loadedExecution.status,
        tabType: 'result'
      });
    } catch {
      if (sequence !== loadSequence || $page.params.id !== executionId) return;
      result = null;
      previewData = null;
      previewPage = 0;
      previewTotalElements = 0;
      previewTotalPages = 0;
      execution = null;
      localizedEntity = null;
      localizedColumns = [];
      error = $t('apiUnavailable');
    } finally {
      if (sequence === loadSequence) loading = false;
    }
  }

  const kpis = $derived(normalizeCards(result?.kpis));
  const metrics = $derived(normalizeCards(
    result?.metrics ?? metricItems(result?.kpis) ?? extractMetrics(result?.kpis)
  ));
  const previewRows = $derived(normalizeRows(previewData));
  const warnings = $derived(normalizeWarnings(
    result?.warnings,
    previewTotalElements,
    previewSize,
    result?.rowCount ?? previewRows.length
  ));
  const columns = $derived(previewRows.length ? Object.keys(previewRows[0]) : []);
  const columnTypes = $derived(normalizeColumnTypes(previewData));
  const columnLabels = $derived(normalizeColumnLabels(previewData));
  const charts = $derived(normalizeCharts(result?.charts));
  const isMl = $derived(Boolean(execution?.executionType?.toUpperCase().includes('ML') || metrics.length));
  const orderPayload = $derived.by(() => {
    const payload = execution?.order?.payload;
    return payload && typeof payload === 'object'
      ? payload as Record<string, unknown>
      : {};
  });
  const temporalGranularities = $derived.by(() => {
    if (!Array.isArray(orderPayload.temporalGroupBy)) return {} as Record<string, string>;
    return Object.fromEntries(orderPayload.temporalGroupBy.flatMap((value) => {
      if (!value || typeof value !== 'object') return [];
      const group = value as Record<string, unknown>;
      return typeof group.alias === 'string' && typeof group.granularity === 'string'
        ? [[group.alias, group.granularity]]
        : [];
    }));
  });
  const tunedAlgorithm = $derived.by(() => {
    if (!Array.isArray(result?.kpis)) return null;
    const selected = result.kpis.find((item) => {
      if (!item || typeof item !== 'object') return false;
      const record = item as Record<string, unknown>;
      return record.code === 'SELECTED_ALGORITHM'
        || record.labelKey === 'result.metric.selectedAlgorithm';
    });
    if (!selected || typeof selected !== 'object') return null;
    const value = (selected as Record<string, unknown>).value;
    return typeof value === 'string' ? value : null;
  });
  const modelName = $derived.by(() => {
    const algorithm = tunedAlgorithm
      ?? orderPayload.algorithm
      ?? execution?.order?.selectedAlgorithm;
    if (typeof algorithm !== 'string') return '—';
    if (tunedAlgorithm) {
      return humanizeField(
        tunedAlgorithm,
        $locale === 'tr' ? 'tr-TR' : 'en-US'
      );
    }
    const parameters = orderPayload.parameters;
    const parameterText = parameters && typeof parameters === 'object'
      ? Object.entries(parameters as Record<string, unknown>)
          .map(([name, value]) => `${humanizeField(name)} ${formatDisplayValue(value, $locale)}`)
          .join(' · ')
      : '';
    return `${humanizeField(algorithm, $locale === 'tr' ? 'tr-TR' : 'en-US')}${parameterText ? ` · ${parameterText}` : ''}`;
  });
  const requestedAnalysis = $derived.by(() => {
    const target = typeof orderPayload.targetColumn === 'string'
      ? columnDisplayName(orderPayload.targetColumn)
      : '—';
    const features = Array.isArray(orderPayload.featureColumns)
      ? orderPayload.featureColumns.map((item) => columnDisplayName(String(item))).join(', ')
      : '—';
    const split = orderPayload.split && typeof orderPayload.split === 'object'
      ? orderPayload.split as Record<string, unknown>
      : {};
    const selection = orderPayload.selection && typeof orderPayload.selection === 'object'
      ? orderPayload.selection as Record<string, unknown>
      : null;
    const ratio = (value: unknown) =>
      typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';
    const testRatio = typeof split.trainingRatio === 'number'
      ? 1 - split.trainingRatio
      : undefined;
    const splitText = selection
      ? ($locale === 'tr'
          ? `Eğitim: ${ratio(selection.trainingRatio)} · Doğrulama: ${ratio(selection.validationRatio)} · Test: ${ratio(selection.testRatio)}`
          : `Training: ${ratio(selection.trainingRatio)} · Validation: ${ratio(selection.validationRatio)} · Test: ${ratio(selection.testRatio)}`)
      : ($locale === 'tr'
          ? `Eğitim: ${ratio(split.trainingRatio)} · Test: ${ratio(testRatio)}`
          : `Training: ${ratio(split.trainingRatio)} · Test: ${ratio(testRatio)}`);
    return $locale === 'tr'
      ? `${target} tahmini · Girdiler: ${features} · ${splitText}`
      : `Predict ${target} · Inputs: ${features} · ${splitText}`;
  });
  const failureExplanation = $derived(
    execution?.failure?.userExplanation || (execution?.status === 'FAILED' ? $t('sparkJobFailed') : '')
  );

  function columnDisplayName(columnName: string): string {
    const normalized = columnName.trim().toLocaleLowerCase('en-US').replaceAll(' ', '_');
    return localizedColumns.find((column) =>
      column.columnName.toLocaleLowerCase('en-US') === normalized
      || column.businessName.toLocaleLowerCase('en-US').replaceAll(' ', '_') === normalized
      || column.businessNameTr?.toLocaleLowerCase('tr-TR').replaceAll(' ', '_') === normalized
    )?.businessName
      ?? humanizeField(columnName, $locale === 'tr' ? 'tr-TR' : 'en-US');
  }

  function normalizeCards(value: unknown): Array<{ label: string; value: string }> {
    if (Array.isArray(value)) return value.flatMap((item, index) => {
      const record = item as Record<string, unknown>;
      const code = String(record.code ?? '');
      if (code === 'SELECTED_ALGORITHM') return [];
      const localizedLabel = {
        BEST_VALIDATION_SCORE: $t('bestValidationScore'),
        CANDIDATES_EVALUATED: $t('tuningTrialsEvaluated'),
        TUNING_TRIALS_EVALUATED: $t('tuningTrialsEvaluated'),
        CANDIDATE_ALGORITHMS_EVALUATED: $t('candidateAlgorithmsEvaluated')
      }[code];
      const rawLabel = localizedLabel
        ?? String(record.label ?? record.code ?? record.labelKey ?? record.name ?? `#${index + 1}`);
      return [{
        label: humanizeField(rawLabel, $locale === 'tr' ? 'tr-TR' : 'en-US'),
        value: formatDisplayValue(record.value ?? record.metric, $locale === 'tr' ? 'tr-TR' : 'en-US')
      }];
    });
    if (value && typeof value === 'object') return Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => ['string', 'number', 'boolean'].includes(typeof item))
      .map(([label, value]) => ({
        label: humanizeField(label, $locale === 'tr' ? 'tr-TR' : 'en-US'),
        value: formatDisplayValue(value, $locale === 'tr' ? 'tr-TR' : 'en-US')
      }));
    return [];
  }

  function extractMetrics(value: unknown) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
    return (value as Record<string, unknown>).metrics;
  }

  function metricItems(value: unknown) {
    if (!Array.isArray(value)) return undefined;
    const metricOrder = [
      'RMSE', 'MAE', 'R2', 'ACCURACY', 'F1', 'PRECISION', 'RECALL', 'AUC'
    ];
    const metricCodes = new Set(metricOrder);
    return value.filter((item) => {
      if (!item || typeof item !== 'object') return false;
      return metricCodes.has(String((item as Record<string, unknown>).code ?? '').toUpperCase());
    }).sort((left, right) =>
      metricOrder.indexOf(String((left as Record<string, unknown>).code).toUpperCase())
      - metricOrder.indexOf(String((right as Record<string, unknown>).code).toUpperCase())
    );
  }

  function kpiValueClass(value: string): string {
    if (value.length > 28) return 'text-base';
    if (value.length > 18) return 'text-lg';
    return 'text-2xl';
  }

  function normalizeWarnings(
    value: unknown,
    availableRows: number,
    pageSize: number,
    totalRows: number
  ): string[] {
    const normalized = Array.isArray(value) ? value.flatMap((item) => {
      if (typeof item === 'string') return item.trim() ? [item] : [];
      if (!item || typeof item !== 'object') return [];
      const warning = item as Record<string, unknown>;
      if (warning.code === 'RESULT_TRUNCATED') return [];
      if (warning.code === 'WHAT_IF_NOT_CAUSAL') return [$t('whatIfNotCausal')];
      return typeof warning.message === 'string' && warning.message.trim()
        ? [warning.message]
        : [];
    }) : typeof value === 'string' && value.trim() ? [value] : [];
    if (availableRows > pageSize) {
      normalized.unshift($t('resultRowsPaged', { size: pageSize }));
    }
    if (totalRows > availableRows) {
      normalized.push($t('resultRowsLimited', {
        shown: availableRows,
        total: totalRows
      }));
    }
    return [...new Set(normalized)];
  }

  async function loadPreview(targetPage: number, targetSize: number) {
    const executionId = $page.params.id;
    if (!executionId || !result) return;
    previewLoading = true;
    try {
      const loadedPage = await api.result(executionId, targetPage, targetSize);
      previewData = loadedPage.preview;
      previewPage = loadedPage.previewPage;
      previewSize = loadedPage.previewSize;
      previewTotalElements = loadedPage.previewTotalElements;
      previewTotalPages = loadedPage.previewTotalPages;
      error = '';
    } catch {
      error = $t('apiUnavailable');
    } finally {
      previewLoading = false;
    }
  }

  function normalizeRows(value: unknown): Array<Record<string, unknown>> {
    if (Array.isArray(value)) return value.filter((item) => item && typeof item === 'object') as Array<Record<string, unknown>>;
    if (value && typeof value === 'object') {
      const rows = (value as Record<string, unknown>).rows;
      if (Array.isArray(rows)) return rows as Array<Record<string, unknown>>;
    }
    return [];
  }

  function normalizeColumnTypes(value: unknown): Record<string, string> {
    if (!value || typeof value !== 'object') return {};
    const metadata = (value as Record<string, unknown>).columns;
    if (!Array.isArray(metadata)) return {};
    return Object.fromEntries(metadata.flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const column = item as Record<string, unknown>;
      return typeof column.name === 'string'
        ? [[column.name, String(column.type ?? '')]]
        : [];
    }));
  }

  function normalizeColumnLabels(value: unknown): Record<string, string> {
    if (!value || typeof value !== 'object') return {};
    const metadata = (value as Record<string, unknown>).columns;
    if (!Array.isArray(metadata)) return {};
    return Object.fromEntries(metadata.flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const column = item as Record<string, unknown>;
      return typeof column.name === 'string' && typeof column.label === 'string'
        ? [[column.name, column.label]]
        : [];
    }));
  }

  function featureDisplayName(value: string): string {
    const encoded = /^__kozmik_encoded_(\d+)_(.+)$/.exec(value);
    if (!encoded) return columnDisplayName(value);
    const featureColumns = Array.isArray(orderPayload.featureColumns)
      ? orderPayload.featureColumns.map(String)
      : [];
    const source = featureColumns[Number(encoded[1])] ?? value;
    const category = encoded[2] === '__unknown' ? $t('unknown') : encoded[2];
    return `${columnDisplayName(source)}: ${category}`;
  }

  function formatResultValue(value: unknown, column: string): string {
    const granularity = temporalGranularities[column];
    return granularity
      ? formatTemporalBucket(value, granularity)
      : formatDisplayValue(
          value,
          $locale === 'tr' ? 'tr-TR' : 'en-US',
          columnTypes[column]
        );
  }

  function resultColumnLabel(column: string): string {
    const granularity = temporalGranularities[column];
    if (!granularity) {
      return columnLabels[column]
        ?? humanizeField(column, $locale === 'tr' ? 'tr-TR' : 'en-US');
    }
    if ($locale === 'tr') {
      return ({
        DAY: 'Gün',
        WEEK: 'Hafta',
        MONTH: 'Ay',
        QUARTER: 'Çeyrek',
        YEAR: 'Yıl'
      } as Record<string, string>)[granularity.toUpperCase()]
        ?? humanizeField(column, 'tr-TR');
    }
    return humanizeField(column, 'en-US');
  }

  function normalizeCharts(value: unknown): Array<{
    title: string;
    summary: string;
    option: EChartsOption;
    bars: Array<{ label: string; value: number }>;
  }> {
    if (!Array.isArray(value)) return [];
    return value.map((raw, index) => {
      const item = raw as Record<string, unknown>;
      const nestedSeries = Array.isArray(item.series)
        ? item.series as Array<Record<string, unknown>>
        : [];
      const normalizedChartId = String(item.chartId ?? item.titleKey ?? '')
        .toLowerCase().replaceAll(/[^a-z]/g, '');
      const genericReportTitle = String(item.titleKey ?? '') === 'result.chart.report';
      const approvedChartHints = Array.isArray(orderPayload.chartHints)
        ? orderPayload.chartHints as Array<Record<string, unknown>>
        : [];
      const approvedValueColumn = String(
        approvedChartHints[index]?.valueColumn ?? item.valueField ?? ''
      );
      const title = genericReportTitle
        ? columnDisplayName(
            approvedValueColumn || String(nestedSeries[0]?.name ?? item.name ?? '')
          )
        : normalizedChartId.includes('whatifanalysis')
        ? $t('whatIfAnalysis')
        : normalizedChartId.includes('featureimportance')
          ? $t('featureImportance')
          : humanizeField(
            String(item.title ?? item.name ?? item.titleKey ?? `${$t('charts')} ${index + 1}`),
            $locale === 'tr' ? 'tr-TR' : 'en-US'
          );
      const fallbackFeatures = item.chartId === 'feature-importance'
        && Array.isArray(orderPayload.featureColumns)
        ? orderPayload.featureColumns.map(String)
        : [];
      const scenarioFacts = Array.isArray(item.scenarioFacts)
        ? item.scenarioFacts.filter((fact) => fact && typeof fact === 'object') as Array<Record<string, unknown>>
        : [];
      const scenarioLabel = (code: string): string => {
        const fact = scenarioFacts.find((candidate) => String(candidate.code ?? '') === code);
        const changes = fact && Array.isArray(fact.changes)
          ? fact.changes.filter((change) => change && typeof change === 'object') as Array<Record<string, unknown>>
          : [];
        if (!changes.length) return humanizeField(code, $locale === 'tr' ? 'tr-TR' : 'en-US');
        return changes.map((change) => {
          const percent = Number(change.percentChange ?? 0);
          const formattedPercent = new Intl.NumberFormat(
            $locale === 'tr' ? 'tr-TR' : 'en-US',
            { maximumFractionDigits: 2, signDisplay: 'always' }
          ).format(percent);
          return `${columnDisplayName(String(change.column ?? ''))} ${formattedPercent}%`;
        }).join(', ');
      };
      const previewCategories = typeof item.categoryField === 'string'
        ? previewRows.map((row) => row[item.categoryField as string])
            .filter((value) => value != null)
        : [];
      const categoryField = typeof item.categoryField === 'string'
        ? item.categoryField
        : undefined;
      const rawLabels = ((
        item.labels
        ?? item.categories
        ?? (previewCategories.length ? previewCategories : fallbackFeatures)
      ) as unknown[]).map((label) =>
        categoryField && temporalGranularities[categoryField]
          ? formatTemporalBucket(label, temporalGranularities[categoryField])
          : String(label)
      );
      const rawValues = (item.values ?? item.data ?? nestedSeries[0]?.data ?? []) as number[];
      const retainedIndexes = rawLabels.flatMap((_, labelIndex) => {
        if (!normalizedChartId.includes('featureimportance')) return [labelIndex];
        const chartValues = nestedSeries.length
          ? nestedSeries.map((entry) => Number(
              Array.isArray(entry.data) ? entry.data[labelIndex] ?? 0 : 0
            ))
          : [Number(rawValues[labelIndex] ?? 0)];
        return chartValues.some((chartValue) => Math.abs(chartValue) > 1e-12)
          ? [labelIndex]
          : [];
      });
      const labels = retainedIndexes.map((labelIndex) =>
        normalizedChartId.includes('featureimportance')
          ? featureDisplayName(rawLabels[labelIndex])
          : normalizedChartId.includes('whatifanalysis')
            ? scenarioLabel(rawLabels[labelIndex])
          : columnDisplayName(rawLabels[labelIndex])
      );
      const values = retainedIndexes.map((labelIndex) => rawValues[labelIndex]);
      const provided = item.option as EChartsOption | undefined;
      const chartType = String(item.type ?? '').toUpperCase();
      const generatedOption = chartType === 'PIE'
        ? {
            tooltip: { trigger: 'item' },
            legend: {
              type: 'scroll',
              bottom: 0
            },
            series: [{
              name: nestedSeries.length
                ? humanizeField(
                    String(nestedSeries[0].name ?? ''),
                    $locale === 'tr' ? 'tr-TR' : 'en-US'
                  )
                : title,
              type: 'pie',
              radius: ['38%', '68%'],
              center: ['50%', '44%'],
              avoidLabelOverlap: true,
              data: labels.map((label, labelIndex) => ({
                name: label,
                value: Number(
                  nestedSeries.length && Array.isArray(nestedSeries[0].data)
                    ? nestedSeries[0].data[retainedIndexes[labelIndex]]
                    : values[labelIndex] ?? 0
                )
              }))
            }]
          } as EChartsOption
        : {
            tooltip: { trigger: 'axis' },
            legend: nestedSeries.length > 1
              ? { type: 'scroll', top: 0 }
              : undefined,
            grid: {
              left: 40,
              right: 16,
              top: nestedSeries.length > 1 ? 42 : 18,
              bottom: normalizedChartId.includes('whatifanalysis') ? 92 : 48
            },
            xAxis: {
              type: 'category',
              data: labels,
              axisLabel: {
                rotate: labels.length > 4 || labels.some((label) => label.length > 18) ? 25 : 0,
                interval: 0
              }
            },
            yAxis: { type: 'value' },
            series: nestedSeries.length
              ? nestedSeries.map((entry) => {
                  const entryData = Array.isArray(entry.data) ? entry.data : [];
                  return {
                    name: String(entry.name ?? '').toLowerCase() === 'importance'
                      ? $t('importance')
                      : humanizeField(
                          String(entry.name ?? ''),
                          $locale === 'tr' ? 'tr-TR' : 'en-US'
                        ),
                    type: chartType === 'LINE' ? 'line' : 'bar',
                    data: retainedIndexes.map((labelIndex) => entryData[labelIndex])
                  };
                })
              : [{
                  type: chartType === 'LINE' ? 'line' : 'bar',
                  data: values
                }]
          } as EChartsOption;
      return {
        title,
        summary: String(item.summary ?? `${title}: ${values.slice(0, 5).join(', ')}`),
        option: provided ?? generatedOption,
        bars: labels.map((label, valueIndex) => ({
          label: humanizeField(label, $locale === 'tr' ? 'tr-TR' : 'en-US'),
          value: Number(values[valueIndex] ?? 0)
        }))
      };
    });
  }

  function stageLabel(stage: string) {
    if (stage === 'RESOLVING_DATA') return $t('resolvingData');
    if (stage === 'TUNING') return $t('tuningModels');
    return stage.replaceAll('_', ' ');
  }

  async function afterDelete() {
    if (!execution) return;
    closeExecutionWorkspace(execution.id);
    await goto('/results');
  }
</script>

<div class="pdf-document">
<div class="pdf-brand"><strong>{$t('brand')}</strong><span>{$t('governedAnalytics')}</span></div>
<PageHeader title={$t('resultTitle')} description={result?.executionId}>
  {#snippet actions()}
    <div class="flex flex-wrap justify-end gap-2">
      {#if execution && result && execution.status === 'SUCCEEDED'}
        <PdfExportButton documentId={execution.id} documentType="result" />
      {/if}
      {#if execution}
        <DeleteExecutionButton executionId={execution.id} onDeleted={afterDelete} />
      {/if}
      <Button href={`/executions/${$page.params.id}`} variant="outline" size="sm"><ArrowLeft size={16} />{$t('back')}</Button>
    </div>
  {/snippet}
</PageHeader>
<StateView loading={loading && !execution && !result} {error} onretry={() => load($page.params.id!)} />
{#if execution?.status === 'FAILED'}
  <Card.Root class="mb-4">
    <Card.Header class="flex-row items-start justify-between gap-4">
      <div class="min-w-0">
        <Card.Description>{$t('originalRequest')}</Card.Description>
        <Card.Title class="mt-1 text-base leading-relaxed">{execution.originalRequest ?? '—'}</Card.Title>
      </div>
      <StatusBadge status={execution.status} />
    </Card.Header>
  </Card.Root>

  <Alert.Root variant="destructive" class="mb-4">
    <TriangleAlert />
    <Alert.Title>{$t('failureReason')}</Alert.Title>
    <Alert.Description class="space-y-3 leading-relaxed">
      <p>{failureExplanation}</p>
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

  {#if execution.history.length}
    <Card.Root class="pdf-breakable pdf-exclude">
      <Card.Header>
        <Card.Title class="text-base">{$t('timeline')}</Card.Title>
        <Card.Description>{execution.history.length} {$t('status')}</Card.Description>
      </Card.Header>
      <Card.Content>
        <ol>
          {#each execution.history as item, index}
            <li class="grid grid-cols-[auto_1fr_auto] gap-3 py-3">
              <span class="mt-1.5 size-2.5 rounded-full bg-muted-foreground"></span>
              <div>
                <strong class="text-sm">{stageLabel(item.stage)}</strong>
                <small class="block text-xs text-muted-foreground">
                  {formatDate(item.occurredAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}
                </small>
                <p class="mt-1 text-sm text-muted-foreground">{item.messageCode}</p>
              </div>
              <Badge variant="secondary">{item.progressPercent}%</Badge>
            </li>
            {#if index < execution.history.length - 1}<Separator />{/if}
          {/each}
        </ol>
      </Card.Content>
    </Card.Root>
  {/if}
{/if}
{#if result}
  {#if execution}
    <Card.Root class="mb-4 pdf-narrative-card">
      <Card.Header class="flex-row items-start justify-between gap-4">
        <div class="min-w-0">
          <Card.Description>{$t('originalRequest')}</Card.Description>
          <p class="pdf-narrative-content mt-1 text-base leading-relaxed">{execution.originalRequest ?? '—'}</p>
        </div>
        <Dialog.Root>
          <Dialog.Trigger>
            {#snippet child({ props })}<Button {...props} variant="outline" size="sm">{$t('technicalDetails')}</Button>{/snippet}
          </Dialog.Trigger>
          <Dialog.Content class="max-w-2xl">
            <Dialog.Header><Dialog.Title>{$t('plan')}</Dialog.Title><Dialog.Description>{execution.id}</Dialog.Description></Dialog.Header>
            <JsonDisplay
              value={execution.order}
              copyLabel={$t('copyJson')}
              copiedLabel={$t('copied')}
            />
          </Dialog.Content>
        </Dialog.Root>
      </Card.Header>
    </Card.Root>
  {/if}

  {#if result.rowCount === 0}
    <Alert.Root class="mb-4">
      <Info />
      <Alert.Title>{$t('emptyExecutionResultTitle')}</Alert.Title>
      <Alert.Description>{$t('emptyExecutionResultBody')}</Alert.Description>
    </Alert.Root>
  {:else}
  <Card.Root class="mb-4 pdf-narrative-card">
    <Card.Header>
      <div class="min-w-0">
        <Card.Description>{$t('summary')}</Card.Description>
        {#if result.managementSummary}<p class="pdf-narrative-content mt-1 w-full text-base leading-relaxed">{formatManagementSummary(result.managementSummary)}</p>
        {:else if result.summaryStatus === 'FAILED'}
          <Alert.Root class="mt-1"><TriangleAlert /><Alert.Description>{$t('summaryFailed')}</Alert.Description></Alert.Root>
        {:else}<p class="mt-1 text-sm text-muted-foreground">{$t('summaryPending')}</p>{/if}
      </div>
    </Card.Header>
  </Card.Root>

  {#if warnings.length}
    <section class="pdf-exclude mb-4" aria-labelledby="warnings-title">
      <h2 id="warnings-title" class="mb-3 text-lg font-semibold">{$t('warnings')}</h2>
      <div class="grid gap-2">
        {#each warnings as warning}
          <Alert.Root><TriangleAlert /><Alert.Description>{warning}</Alert.Description></Alert.Root>
        {/each}
      </div>
    </section>
  {/if}

  {#if isMl}
    <section class="pdf-ml-overview mb-4 grid gap-4 lg:grid-cols-3" aria-label={$t('metrics')}>
      <Card.Root><Card.Header class="flex-row items-center gap-3"><span class="pdf-decorative-icon flex size-9 items-center justify-center rounded-md bg-muted"><ClipboardList size={18} /></span><div><Card.Description>{$t('requestedAnalysis')}</Card.Description><Card.Title class="text-base">{requestedAnalysis}</Card.Title></div></Card.Header></Card.Root>
      <Card.Root><Card.Header class="flex-row items-center gap-3"><span class="pdf-decorative-icon flex size-9 items-center justify-center rounded-md bg-muted"><BrainCircuit size={18} /></span><div><Card.Description>{$t('modelUsed')}</Card.Description><Card.Title class="text-base">{modelName}</Card.Title></div></Card.Header></Card.Root>
      <Card.Root><Card.Header class="flex-row items-center gap-3"><span class="pdf-decorative-icon flex size-9 items-center justify-center rounded-md bg-muted"><Gauge size={18} /></span><div class="min-w-0"><Card.Description>{$t('reliability')}</Card.Description><Card.Title class="break-words text-base">{metrics.map((item) => `${item.label}: ${item.value}`).join(' · ') || '—'}</Card.Title></div></Card.Header></Card.Root>
    </section>
  {/if}

  {#if kpis.length}
    <section aria-labelledby="kpis-title">
      <h2 id="kpis-title" class="mb-3 mt-4 text-lg font-semibold">{$t('kpis')}</h2>
      <div class="pdf-kpi-grid grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {#each kpis as kpi}
          <Card.Root class="min-w-0">
            <Card.Header class="min-w-0">
              <Card.Description>{kpi.label}</Card.Description>
              <Card.Title
                class={`${kpiValueClass(kpi.value)} min-w-0 break-words leading-tight [overflow-wrap:anywhere]`}
              >
                {kpi.value}
              </Card.Title>
            </Card.Header>
          </Card.Root>
        {/each}
      </div>
    </section>
  {/if}

  {#if charts.length}
    <section aria-labelledby="charts-title">
      <h2 id="charts-title" class="mb-3 mt-4 text-lg font-semibold">{$t('charts')}</h2>
      <div class="pdf-chart-grid grid gap-4 lg:grid-cols-2">
        {#each charts as chart}<ChartView {...chart} locale={$locale === 'tr' ? 'tr-TR' : 'en-US'} errorText={$t('chartRenderFailed')} />{/each}
      </div>
    </section>
  {/if}

  {#if metrics.length}
    <section class="pdf-metrics-section" aria-labelledby="metrics-title">
      <h2 id="metrics-title" class="mb-3 mt-4 text-lg font-semibold">{$t('metrics')}</h2>
      <Card.Root><Card.Content class="pdf-metrics-grid grid gap-4 pt-6 sm:grid-cols-2 lg:grid-cols-4">{#each metrics as metric}<div class="grid gap-1"><span class="text-sm text-muted-foreground">{metric.label}</span><strong class="text-lg">{metric.value}</strong></div>{/each}</Card.Content></Card.Root>
    </section>
  {/if}

  <section class="pdf-exclude" aria-labelledby="preview-title">
    <h2 id="preview-title" class="mb-3 mt-4 text-lg font-semibold">{$t('preview')}</h2>
    <Card.Root class="pdf-breakable">
      <Card.Header><Card.Title class="flex items-center gap-2 text-base"><Info size={17} />{$t('previewPageRows', {
        from: previewTotalElements ? previewPage * previewSize + 1 : 0,
        to: Math.min((previewPage + 1) * previewSize, previewTotalElements),
        total: previewTotalElements
      })}</Card.Title><Card.Description>{$t('previewLimited', {
        total: previewTotalElements,
        size: previewSize
      })}</Card.Description></Card.Header>
      <Card.Content>
      {#if previewRows.length}
        <div class="overflow-x-auto">
          <Table.Root><Table.Header><Table.Row>{#each columns as column}<Table.Head>{resultColumnLabel(column)}</Table.Head>{/each}</Table.Row></Table.Header><Table.Body>
            {#each previewRows as row}<Table.Row>{#each columns as column}<Table.Cell>{formatResultValue(row[column], column)}</Table.Cell>{/each}</Table.Row>{/each}
          </Table.Body></Table.Root>
        </div>
      {:else}<p class="text-sm text-muted-foreground">{$t('noData')}</p>{/if}
      <ServerPagination
        page={previewPage}
        size={previewSize}
        totalElements={previewTotalElements}
        totalPages={previewTotalPages}
        disabled={previewLoading}
        onPage={(value) => void loadPreview(value, previewSize)}
        onSize={(value) => void loadPreview(0, value)}
      />
      </Card.Content>
    </Card.Root>
  </section>

  <section class="pdf-exclude" aria-labelledby="artifact-title">
    <h2 id="artifact-title" class="mb-3 mt-4 text-lg font-semibold">{$t('artifact')}</h2>
    <Card.Root>
      <Card.Header class="flex-row items-center gap-3">
        <span class="flex size-10 items-center justify-center rounded-md bg-muted"><Box /></span>
        <div class="min-w-0 flex-1"><Card.Title class="truncate text-base">Parquet · {result.artifact.artifactId}</Card.Title><Card.Description>{$t('artifactGuidance')}</Card.Description></div>
      </Card.Header>
      <Card.Content><p class="text-sm text-muted-foreground">{$t('reporterGuidance')}</p></Card.Content>
    </Card.Root>
  </section>

  {#if execution?.history?.length}
    <section class="pdf-exclude" aria-labelledby="timeline-title">
      <h2 id="timeline-title" class="mb-3 mt-4 text-lg font-semibold">{$t('timeline')}</h2>
      <Card.Root class="pdf-breakable">
        <Card.Header>
          <Card.Title class="text-base">{$t('timeline')}</Card.Title>
          <Card.Description>{execution.history.length} {$t('status')}</Card.Description>
        </Card.Header>
        <Card.Content>
          <ol>
            {#each execution.history as item, index}
              <li class="grid grid-cols-[auto_1fr_auto] gap-3 py-3">
                <span class={`mt-1.5 size-2.5 rounded-full ${item.progressPercent === 100 ? 'bg-primary' : 'bg-muted-foreground'}`}></span>
                <div>
                  <strong class="text-sm">{stageLabel(item.stage)}</strong>
                  <small class="block text-xs text-muted-foreground">{formatDate(item.occurredAt, $locale === 'tr' ? 'tr-TR' : 'en-US')}</small>
                  <p class="mt-1 text-sm text-muted-foreground">{item.messageCode}</p>
                </div>
                <Badge variant="secondary">{item.progressPercent}%</Badge>
              </li>
              {#if index < execution.history.length - 1}<Separator />{/if}
            {/each}
          </ol>
        </Card.Content>
      </Card.Root>
    </section>
  {/if}

  <Card.Root class="pdf-production-card mt-4">
    <Card.Header><Card.Title class="text-base">{$t('howProduced')}</Card.Title></Card.Header>
    <Card.Content class="grid gap-4 sm:grid-cols-2">
      {#each [
        [$t('entity'), $locale === 'tr'
          ? (localizedEntity?.nameTr ?? localizedEntity?.name ?? execution?.entityName ?? '—')
          : (localizedEntity?.canonicalName ?? localizedEntity?.name ?? execution?.entityName ?? '—')],
        [$t('entityId'), execution?.entityId ?? '—'],
        [$t('type'), execution?.executionType?.toUpperCase().includes('ML')
          ? $t('ml') : $t('report')],
        [$t('executionId'), result.executionId]
      ] as fact}
        <div><p class="text-xs text-muted-foreground">{fact[0]}</p><code class="break-all text-sm">{fact[1]}</code></div>
      {/each}
    </Card.Content>
  </Card.Root>
  {/if}
{/if}
</div>

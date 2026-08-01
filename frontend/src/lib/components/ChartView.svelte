<script lang="ts">
  import { onMount } from 'svelte';
  import type { ECharts, EChartsOption } from 'echarts';
  import * as Card from './ui/card/index.js';

  let {
    title,
    option,
    summary,
    bars = [],
    locale = 'en-US',
    errorText = 'The chart could not be rendered.'
  }: {
    title: string;
    option: EChartsOption;
    summary: string;
    bars?: Array<{ label: string; value: number }>;
    locale?: string;
    errorText?: string;
  } = $props();
  let container: HTMLDivElement;
  let chart = $state.raw<ECharts | undefined>();
  let renderError = $state(false);
  let frame: number | undefined;
  const maximumBarValue = $derived(Math.max(...bars.map((item) => Math.abs(item.value)), 1));

  onMount(() => {
    let observer: ResizeObserver | undefined;
    let themeObserver: MutationObserver | undefined;
    let printObserver: MutationObserver | undefined;
    let disposed = false;
    const resizeChart = () => {
      if (container.clientWidth <= 0) return;
      const height = document.body.classList.contains('pdf-exporting') ? 180 : 300;
      chart?.resize({ width: container.clientWidth, height });
    };
    const prepareForPrint = () => {
      chart?.setOption(chartOption(), true);
      chart?.resize({ width: container.getBoundingClientRect().width, height: 180 });
    };
    const restoreAfterPrint = () => {
      chart?.resize({ width: container.getBoundingClientRect().width, height: 300 });
    };
    void import('echarts').then((echarts) => {
      if (disposed) return;
      chart = echarts.init(container, undefined, { renderer: 'svg', height: 300 });
      chart.setOption(chartOption(), true);
      renderError = false;
      observer = new ResizeObserver(() => {
        resizeChart();
      });
      observer.observe(container);
      themeObserver = new MutationObserver(() => {
        chart?.setOption(chartOption(), true);
      });
      themeObserver.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['class']
      });
      printObserver = new MutationObserver(() => {
        chart?.setOption(chartOption(), true);
        requestAnimationFrame(resizeChart);
      });
      printObserver.observe(document.body, {
        attributes: true,
        attributeFilter: ['class']
      });
      window.addEventListener('beforeprint', prepareForPrint);
      window.addEventListener('afterprint', restoreAfterPrint);
    }).catch((error: unknown) => {
      console.error('ECharts initialization failed', error);
      renderError = true;
    });
    return () => {
      disposed = true;
      if (frame !== undefined) cancelAnimationFrame(frame);
      observer?.disconnect();
      themeObserver?.disconnect();
      printObserver?.disconnect();
      window.removeEventListener('beforeprint', prepareForPrint);
      window.removeEventListener('afterprint', restoreAfterPrint);
      chart?.dispose();
    };
  });

  $effect(() => {
    option;
    if (chart) {
      if (frame !== undefined) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        try {
          chart?.setOption(chartOption(), true);
          renderError = false;
        } catch (error) {
          console.error('ECharts option rendering failed', error);
          renderError = true;
        }
      });
    }
  });

  function chartOption(): EChartsOption {
    const dark = document.documentElement.classList.contains('dark');
    const foreground = dark ? '#f5f5f5' : '#171717';
    const mutedForeground = dark ? '#a3a3a3' : '#737373';
    const border = dark ? '#404040' : '#e5e5e5';
    const surface = dark ? '#262626' : '#ffffff';
    const palette = dark
      ? ['#f5f5f5', '#a3a3a3', '#737373', '#d4d4d4', '#525252']
      : ['#171717', '#525252', '#737373', '#a3a3a3', '#d4d4d4'];
    const configured = option as Record<string, unknown>;
    const configuredSeries = Array.isArray(configured.series)
      ? configured.series as Array<Record<string, unknown>>
      : configured.series && typeof configured.series === 'object'
        ? [configured.series as Record<string, unknown>]
        : [];
    const containsPie = configuredSeries.some((item) => item.type === 'pie');
    const barSeriesCount = configuredSeries.filter((item) => item.type === 'bar').length;
    const themedSeries = configuredSeries.map((series) => series.type === 'bar'
      ? {
          ...series,
          colorBy: series.colorBy ?? (barSeriesCount === 1 ? 'data' : 'series')
        }
      : series
    );
    const configuredTooltip = configured.tooltip && typeof configured.tooltip === 'object'
      ? configured.tooltip as Record<string, unknown>
      : {};
    return {
      backgroundColor: 'transparent',
      color: palette,
      textStyle: {
        color: foreground,
        fontFamily: 'Inter, system-ui, sans-serif'
      },
      animation: false,
      ...option,
      series: themedSeries as EChartsOption['series'],
      xAxis: themedAxes(
        configured.xAxis, foreground, mutedForeground, border
      ) as EChartsOption['xAxis'],
      yAxis: themedAxes(
        configured.yAxis, foreground, mutedForeground, border
      ) as EChartsOption['yAxis'],
      tooltip: {
        trigger: containsPie ? 'item' : 'axis',
        ...configuredTooltip,
        show: true,
        triggerOn: 'mousemove|click|mousewheel',
        renderMode: 'html',
        confine: true,
        enterable: false,
        backgroundColor: surface,
        borderColor: border,
        textStyle: { color: foreground },
        extraCssText: [
          'border-radius: 8px',
          'padding: 8px 10px',
          'box-shadow: 0 8px 24px rgba(0,0,0,.16)',
          'font-family: Inter, system-ui, sans-serif'
        ].join(';'),
        valueFormatter: (value: unknown) => {
          const numeric = Number(value);
          return Number.isFinite(numeric)
            ? new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(numeric)
            : String(value ?? '—');
        }
      }
    };
  }

  function themedAxes(
    axes: unknown,
    foreground: string,
    mutedForeground: string,
    border: string
  ): unknown {
    if (!axes) return axes;
    const values = Array.isArray(axes) ? axes : [axes];
    const themed = values.map((axis) => {
      const configured = axis && typeof axis === 'object'
        ? axis as Record<string, unknown>
        : {};
      return {
        ...configured,
        axisLine: {
          ...(configured.axisLine as Record<string, unknown> ?? {}),
          lineStyle: { color: border }
        },
        axisTick: {
          ...(configured.axisTick as Record<string, unknown> ?? {}),
          lineStyle: { color: border }
        },
        axisLabel: {
          ...(configured.axisLabel as Record<string, unknown> ?? {}),
          color: mutedForeground
        },
        nameTextStyle: {
          ...(configured.nameTextStyle as Record<string, unknown> ?? {}),
          color: foreground
        },
        splitLine: {
          ...(configured.splitLine as Record<string, unknown> ?? {}),
          lineStyle: { color: border }
        }
      };
    });
    return Array.isArray(axes) ? themed : themed[0];
  }

</script>

<Card.Root class="min-w-0">
  <Card.Header>
    <Card.Title>{title}</Card.Title>
  </Card.Header>
  <Card.Content>
    <div
      bind:this={container}
      class="h-[300px] min-h-[300px] w-full cursor-crosshair"
      role="img"
      aria-label={summary}
      data-chart-status={renderError ? 'failed' : chart ? 'ready' : 'loading'}
    ></div>
    {#if renderError}
      {#if bars.length}
        <div class="grid h-[300px] grid-cols-[repeat(auto-fit,minmax(5rem,1fr))] items-end gap-4 border-b border-l px-4 pt-4" role="img" aria-label={summary}>
          {#each bars as bar}
            <div class="grid h-full grid-rows-[1fr_auto] items-end gap-2 text-center">
              <div class="flex h-full items-end justify-center">
                <div
                  class="w-full max-w-20 rounded-t bg-primary"
                  style={`height: ${Math.max(3, Math.abs(bar.value) / maximumBarValue * 100)}%`}
                  title={`${bar.label}: ${bar.value}`}
                ></div>
              </div>
              <span class="break-words pb-2 text-xs text-muted-foreground">{bar.label}</span>
            </div>
          {/each}
        </div>
      {:else}
        <p class="mt-2 text-sm text-destructive">{errorText}</p>
      {/if}
    {/if}
  </Card.Content>
  <Card.Footer class="sr-only">
    <Card.Description>{summary}</Card.Description>
  </Card.Footer>
</Card.Root>

<script lang="ts">
  import { Activity, ChartNoAxesCombined, CircleX, FlaskConical } from '@lucide/svelte';

  let {
    kind,
    status,
    context = 'result',
    class: className
  }: {
    kind: string;
    status: string;
    context?: 'execution' | 'result';
    class?: string;
  } = $props();
</script>

{#if status.toUpperCase() === 'FAILED'}
  <CircleX class={className} aria-hidden="true" />
{:else if context === 'execution'}
  <Activity class={className} aria-hidden="true" />
{:else if kind.toUpperCase().includes('ML')}
  <FlaskConical class={className} aria-hidden="true" />
{:else}
  <ChartNoAxesCombined class={className} aria-hidden="true" />
{/if}

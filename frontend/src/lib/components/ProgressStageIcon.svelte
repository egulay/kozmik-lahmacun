<script lang="ts">
  import {
    Activity,
    Ban,
    BrainCircuit,
    CircleCheckBig,
    CircleX,
    ClipboardList,
    Clock3,
    Database,
    FileOutput,
    Hand,
    Play,
    Settings2,
    ShieldCheck,
    SlidersHorizontal,
    Sparkles,
    TimerOff
  } from '@lucide/svelte';

  let { stage }: { stage: string } = $props();
</script>

<span
  class={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border ${
    stage === 'COMPLETED'
      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
      : stage === 'FAILED' || stage === 'TIMED_OUT'
        ? 'border-destructive/30 bg-destructive/10 text-destructive'
        : stage === 'CANCELLED' || stage === 'CANCELLATION_REQUESTED'
          ? 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400'
          : 'border-border bg-muted text-muted-foreground'
  }`}
  aria-hidden="true"
>
  {#if stage === 'PLANNING'}
    <ClipboardList class="size-4" />
  {:else if stage === 'VALIDATING'}
    <ShieldCheck class="size-4" />
  {:else if stage === 'QUEUED'}
    <Clock3 class="size-4" />
  {:else if stage === 'PREPARING'}
    <Settings2 class="size-4" />
  {:else if stage === 'RESOLVING_DATA'}
    <Database class="size-4" />
  {:else if stage === 'TUNING'}
    <SlidersHorizontal class="size-4" />
  {:else if stage === 'TRAINING'}
    <BrainCircuit class="size-4" />
  {:else if stage === 'RUNNING'}
    <Play class="size-4" />
  {:else if stage === 'WRITING_RESULTS'}
    <FileOutput class="size-4" />
  {:else if stage === 'SUMMARIZING'}
    <Sparkles class="size-4" />
  {:else if stage === 'COMPLETED'}
    <CircleCheckBig class="size-4" />
  {:else if stage === 'FAILED'}
    <CircleX class="size-4" />
  {:else if stage === 'CANCELLED'}
    <Ban class="size-4" />
  {:else if stage === 'TIMED_OUT'}
    <TimerOff class="size-4" />
  {:else if stage === 'CANCELLATION_REQUESTED'}
    <Hand class="size-4" />
  {:else}
    <Activity class="size-4" />
  {/if}
</span>

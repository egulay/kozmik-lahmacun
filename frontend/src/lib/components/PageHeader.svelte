<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    eyebrow,
    title,
    description,
    actions
  }: {
    eyebrow?: string;
    title: string;
    description?: string;
    actions?: Snippet;
  } = $props();
</script>

<header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
  <div>
    {#if eyebrow}<p class="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">{eyebrow}</p>{/if}
    <h1 class="text-2xl font-semibold tracking-tight">{title}</h1>
    {#if description}<p class="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>{/if}
  </div>
  {#if actions}<div class="shrink-0">{@render actions()}</div>{/if}
</header>

<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    eyebrow,
    title,
    description,
    icon,
    actions,
    sticky = false
  }: {
    eyebrow?: string;
    title: string;
    description?: string;
    icon?: Snippet;
    actions?: Snippet;
    sticky?: boolean;
  } = $props();
</script>

<header class={sticky
  ? 'workspace-sticky-header z-30 -mx-4 mb-6 flex flex-col gap-3 border-b bg-background px-4 py-3 md:-mx-6 md:px-6 sm:flex-row sm:items-center sm:justify-between'
  : 'mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between'}>
  <div>
    {#if eyebrow}<p class="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">{eyebrow}</p>{/if}
    <div class="flex items-center gap-2">
      {#if icon}<span class="pdf-decorative-icon shrink-0">{@render icon()}</span>{/if}
      <h1 class="text-2xl font-semibold tracking-tight">{title}</h1>
    </div>
    {#if description}<p class="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>{/if}
  </div>
  {#if actions}<div class="shrink-0">{@render actions()}</div>{/if}
</header>

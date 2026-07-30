<script lang="ts">
  import { Check, Copy } from '@lucide/svelte';
  import { Button } from '$lib/components/ui/button/index.js';

  let {
    value,
    copyLabel = 'Copy JSON',
    copiedLabel = 'Copied'
  }: {
    value: unknown;
    copyLabel?: string;
    copiedLabel?: string;
  } = $props();

  let copied = $state(false);
  let resetTimer: ReturnType<typeof setTimeout> | undefined;
  const json = $derived(JSON.stringify(value, null, 2));

  async function copyJson() {
    await navigator.clipboard.writeText(json);
    copied = true;
    if (resetTimer) clearTimeout(resetTimer);
    resetTimer = setTimeout(() => (copied = false), 2_000);
  }
</script>

<div class="relative min-w-0">
  <Button
    variant="secondary"
    size="icon-sm"
    class="absolute right-2 top-2 z-10"
    aria-label={copied ? copiedLabel : copyLabel}
    title={copied ? copiedLabel : copyLabel}
    onclick={copyJson}
  >
    {#if copied}<Check size={15} />{:else}<Copy size={15} />{/if}
  </Button>
  <pre class="max-h-[60vh] overflow-auto rounded-md bg-muted p-4 pr-12 text-xs whitespace-pre-wrap">{json}</pre>
</div>

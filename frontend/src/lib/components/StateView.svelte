<script lang="ts">
  import { AlertTriangle, RotateCcw } from '@lucide/svelte';
  import { Button } from './ui/button/index.js';
  import { Skeleton } from './ui/skeleton/index.js';
  import * as Alert from './ui/alert/index.js';
  import { t } from '$lib/i18n';

  let {
    loading = false,
    error = '',
    empty = false,
    emptyText,
    onretry
  }: {
    loading?: boolean;
    error?: string;
    empty?: boolean;
    emptyText?: string;
    onretry?: () => void;
  } = $props();
</script>

{#if loading}
  <div class="grid gap-3 py-6" aria-live="polite" aria-label={$t('loading')}>
    <Skeleton class="h-5 w-2/5" />
    <Skeleton class="h-20 w-full" />
    <Skeleton class="h-20 w-full" />
  </div>
{:else if error}
  <Alert.Root
    variant="destructive"
    class="mb-4 min-h-14 items-center gap-x-3 px-4 py-3 has-data-[slot=alert-action]:pr-32"
  >
    <AlertTriangle class="row-span-1! self-center! translate-y-0!" aria-hidden="true" />
    <Alert.Title class="py-1 leading-relaxed">{error}</Alert.Title>
    {#if onretry}
      <Alert.Action class="top-1/2 right-3 -translate-y-1/2">
        <Button variant="outline" size="sm" onclick={onretry}>
          <RotateCcw size={15} aria-hidden="true" /> {$t('retry')}
        </Button>
      </Alert.Action>
    {/if}
  </Alert.Root>
{:else if empty}
  <Alert.Root class="mb-4 px-4 py-3">
    <Alert.Description>{emptyText ?? $t('noData')}</Alert.Description>
  </Alert.Root>
{/if}

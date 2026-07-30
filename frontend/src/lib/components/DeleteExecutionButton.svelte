<script lang="ts">
  import { Trash2 } from '@lucide/svelte';
  import { api } from '$lib/api';
  import {
    beginExecutionDeletion,
    endExecutionDeletion,
    notifyExecutionDeleted
  } from '$lib/execution-deletion';
  import { t } from '$lib/i18n';
  import { Button } from './ui/button/index.js';
  import * as Dialog from './ui/dialog/index.js';

  let {
    executionId,
    compact = false,
    onDeleted
  }: {
    executionId: string;
    compact?: boolean;
    onDeleted: () => void | Promise<void>;
  } = $props();

  let open = $state(false);
  let deleting = $state(false);
  let error = $state('');

  async function remove() {
    deleting = true;
    error = '';
    beginExecutionDeletion(executionId);
    try {
      await api.deleteExecution(executionId);
      notifyExecutionDeleted(executionId);
      open = false;
      await onDeleted();
    } catch {
      error = $t('deleteExecutionFailed');
    } finally {
      endExecutionDeletion(executionId);
      deleting = false;
    }
  }
</script>

<Dialog.Root bind:open>
  <Dialog.Trigger>
    {#snippet child({ props })}
      <Button
        {...props}
        variant="destructive"
        size={compact ? 'icon-sm' : 'sm'}
        aria-label={$t('deleteExecution')}
        title={$t('deleteExecution')}
      >
        <Trash2 size={16} />
        {#if !compact}{$t('delete')}{/if}
      </Button>
    {/snippet}
  </Dialog.Trigger>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>{$t('deleteExecutionTitle')}</Dialog.Title>
      <Dialog.Description>{$t('deleteExecutionBody')}</Dialog.Description>
    </Dialog.Header>
    {#if error}<p class="text-sm text-destructive">{error}</p>{/if}
    <Dialog.Footer>
      <Dialog.Close>
        {#snippet child({ props })}
          <Button {...props} variant="outline" disabled={deleting}>
            {$t('keepExecution')}
          </Button>
        {/snippet}
      </Dialog.Close>
      <Button variant="destructive" disabled={deleting} onclick={remove}>
        <Trash2 size={16} />
        {deleting ? $t('deleting') : $t('delete')}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

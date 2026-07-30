<script lang="ts">
  import { ChevronLeft, ChevronRight } from '@lucide/svelte';
  import { t } from '$lib/i18n';
  import { Button } from './ui/button/index.js';
  import * as Select from './ui/select/index.js';

  let {
    page,
    size,
    totalElements,
    totalPages,
    disabled = false,
    onPage,
    onSize
  }: {
    page: number;
    size: number;
    totalElements: number;
    totalPages: number;
    disabled?: boolean;
    onPage: (page: number) => void;
    onSize: (size: number) => void;
  } = $props();
</script>

<div class="mt-4 flex flex-col gap-3 border-t pt-4 text-sm sm:flex-row sm:items-center sm:justify-between">
  <span class="text-muted-foreground">
    {$t('totalRows')}: {totalElements} · {$t('page')} {totalPages ? page + 1 : 0} / {totalPages}
  </span>
  <div class="flex items-center gap-2">
    <span class="text-muted-foreground">{$t('rowsPerPage')}</span>
    <Select.Root
      type="single"
      value={String(size)}
      onValueChange={(value) => value && onSize(Number(value))}
      disabled={disabled}
    >
      <Select.Trigger class="w-20">{size}</Select.Trigger>
      <Select.Content>
        {#each [5, 10, 20, 50] as option}
          <Select.Item value={String(option)}>{option}</Select.Item>
        {/each}
      </Select.Content>
    </Select.Root>
    <Button
      variant="outline"
      size="icon-sm"
      disabled={disabled || page <= 0}
      aria-label={$t('previousPage')}
      onclick={() => onPage(page - 1)}
    ><ChevronLeft /></Button>
    <Button
      variant="outline"
      size="icon-sm"
      disabled={disabled || page + 1 >= totalPages}
      aria-label={$t('nextPage')}
      onclick={() => onPage(page + 1)}
    ><ChevronRight /></Button>
  </div>
</div>

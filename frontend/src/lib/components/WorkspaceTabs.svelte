<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { X } from '@lucide/svelte';
  import {
    closeWorkspaceTab,
    workspaceTabs,
    type WorkspaceTab
  } from '$lib/workspace-tabs';
  import { t } from '$lib/i18n';
  import { Button } from './ui/button/index.js';
  import * as Tabs from './ui/tabs/index.js';
  import * as Tooltip from './ui/tooltip/index.js';
  import ExecutionTypeIcon from './ExecutionTypeIcon.svelte';

  const activeValue = $derived(
    $page.url.pathname.startsWith('/executions/')
      ? `execution:${$page.params.id}`
      : $page.url.pathname.startsWith('/results/')
        ? `result:${$page.params.id}`
        : ''
  );

  function value(tab: WorkspaceTab) {
    return `${tab.tabType}:${tab.executionId}`;
  }

  function href(tab: WorkspaceTab) {
    return `/${tab.tabType === 'execution' ? 'executions' : 'results'}/${tab.executionId}`;
  }

  async function close(event: MouseEvent, tab: WorkspaceTab) {
    event.preventDefault();
    event.stopPropagation();

    const wasActive = activeValue === value(tab);
    closeWorkspaceTab(tab.tabType, tab.executionId);

    if (!wasActive) return;
    const remaining = $workspaceTabs.filter((item) => value(item) !== value(tab));
    await goto(
      remaining.length
        ? href(remaining.at(-1)!)
        : (tab.tabType === 'execution' ? '/executions' : '/chat')
    );
  }
</script>

{#if $workspaceTabs.length}
  <Tabs.Root
    value={activeValue}
    class="border-b px-4 pt-2"
    aria-label={$t('openExecutions')}
  >
    <Tabs.List class="h-auto max-w-full justify-start overflow-x-auto" variant="line">
      {#each $workspaceTabs as tab (value(tab))}
        <div class="flex shrink-0 items-center">
          <Tooltip.Provider>
            <Tooltip.Root>
              <Tooltip.Trigger>
                {#snippet child({ props })}
                  <Tabs.Trigger
                    {...props}
                    value={value(tab)}
                    class="max-w-52 gap-2"
                    onclick={() => goto(href(tab))}
                  >
                    <ExecutionTypeIcon
                      kind={tab.kind}
                      status={tab.status}
                      context={tab.tabType}
                    />
                    <span class="truncate">{tab.title}</span>
                  </Tabs.Trigger>
                {/snippet}
              </Tooltip.Trigger>
              <Tooltip.Content class="max-w-sm whitespace-normal">
                {tab.title} · {tab.status}
              </Tooltip.Content>
            </Tooltip.Root>
          </Tooltip.Provider>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label={`${$t('closeTab')}: ${tab.title}`}
            onclick={(event) => close(event, tab)}
          >
            <X />
          </Button>
        </div>
      {/each}
    </Tabs.List>
  </Tabs.Root>
{/if}

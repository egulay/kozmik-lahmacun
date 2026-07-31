<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import {
    Activity,
    ChartNoAxesCombined,
    Database,
    MessageSquareText,
    Users,
    X
  } from '@lucide/svelte';
  import {
    closeWorkspaceTab,
    workspaceTabKey,
    workspaceTabResourceId,
    workspaceTabs,
    type WorkspaceTab
  } from '$lib/workspace-tabs';
  import { t } from '$lib/i18n';
  import { Button } from './ui/button/index.js';
  import * as Tabs from './ui/tabs/index.js';
  import * as Tooltip from './ui/tooltip/index.js';
  import ExecutionTypeIcon from './ExecutionTypeIcon.svelte';

  const activeValue = $derived(
    $page.url.pathname === '/chat' && $page.url.searchParams.get('thread')
      ? `chat:${$page.url.searchParams.get('thread')}`
      : $page.url.pathname === '/entities'
        ? 'page:entities'
        : $page.url.pathname === '/executions'
          ? 'page:executions'
          : $page.url.pathname === '/results'
            ? 'page:results'
        : $page.url.pathname.startsWith('/entities/')
          ? `entity:${$page.params.id}`
          : $page.url.pathname === '/admin/users'
            ? 'page:users'
      : $page.url.pathname.startsWith('/executions/')
      ? `execution:${$page.params.id}`
      : $page.url.pathname.startsWith('/results/')
        ? `result:${$page.params.id}`
        : ''
  );

  function value(tab: WorkspaceTab) {
    return workspaceTabKey(tab);
  }

  function href(tab: WorkspaceTab) {
    if (tab.tabType === 'chat') return `/chat?thread=${encodeURIComponent(tab.threadId)}`;
    if (tab.tabType === 'entity') return `/entities/${tab.entityId}`;
    if (tab.tabType === 'page') {
      if (tab.pageId === 'entities') return '/entities';
      if (tab.pageId === 'executions') return '/executions';
      if (tab.pageId === 'results') return '/results';
      return '/admin/users';
    }
    return `/${tab.tabType === 'execution' ? 'executions' : 'results'}/${tab.executionId}`;
  }

  function title(tab: WorkspaceTab) {
    return tab.tabType === 'page' ? $t(tab.pageId) : tab.title;
  }

  async function close(event: MouseEvent, tab: WorkspaceTab) {
    event.preventDefault();
    event.stopPropagation();

    const wasActive = activeValue === value(tab);
    closeWorkspaceTab(tab.tabType, workspaceTabResourceId(tab));

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
    class="w-full min-w-0 overflow-hidden border-b px-4 pt-2"
    aria-label={$t('openExecutions')}
  >
    <div class="w-full min-w-0 overflow-x-auto overscroll-x-contain">
      <Tabs.List class="h-auto min-w-max justify-start" variant="line">
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
                      {#if tab.tabType === 'chat'}
                        <MessageSquareText />
                      {:else if tab.tabType === 'entity' || (tab.tabType === 'page' && tab.pageId === 'entities')}
                        <Database />
                      {:else if tab.tabType === 'page' && tab.pageId === 'executions'}
                        <Activity />
                      {:else if tab.tabType === 'page' && tab.pageId === 'results'}
                        <ChartNoAxesCombined />
                      {:else if tab.tabType === 'page'}
                        <Users />
                      {:else}
                        <ExecutionTypeIcon
                          kind={tab.kind}
                          status={tab.status}
                          context={tab.tabType}
                        />
                      {/if}
                      <span class="truncate">{title(tab)}</span>
                    </Tabs.Trigger>
                  {/snippet}
                </Tooltip.Trigger>
                <Tooltip.Content class="max-w-sm whitespace-normal">
                  {title(tab)}{tab.tabType === 'execution' || tab.tabType === 'result'
                    ? ` · ${tab.status}`
                    : ''}
                </Tooltip.Content>
              </Tooltip.Root>
            </Tooltip.Provider>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`${$t('closeTab')}: ${title(tab)}`}
              onclick={(event) => close(event, tab)}
            >
              <X />
            </Button>
          </div>
        {/each}
      </Tabs.List>
    </div>
  </Tabs.Root>
{/if}

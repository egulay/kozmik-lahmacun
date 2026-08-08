<script lang="ts">
  import { page } from '$app/stores';
  import {
    Activity,
    ChevronsUpDown,
    Database,
    Languages,
    KeyRound,
    LibraryBig,
    LogOut,
    MessageSquareText,
    Users
  } from '@lucide/svelte';
  import type { Snippet } from 'svelte';
  import { onMount } from 'svelte';
  import { locale, setLocale, statusLabel, t } from '$lib/i18n';
  import { currentUser, hasRole, primaryRole } from '$lib/session';
  import { api } from '$lib/api';
  import { deletingExecutionIds } from '$lib/execution-deletion';
  import type { ChatThread, Execution } from '$lib/types';
  import { Button } from './ui/button/index.js';
  import * as Avatar from './ui/avatar/index.js';
  import * as DropdownMenu from './ui/dropdown-menu/index.js';
  import * as Dialog from './ui/dialog/index.js';
  import * as Alert from './ui/alert/index.js';
  import { Badge } from './ui/badge/index.js';
  import * as Tooltip from './ui/tooltip/index.js';
  import * as Sidebar from './ui/sidebar/index.js';
  import WorkspaceTabs from './WorkspaceTabs.svelte';
  import ExecutionTypeIcon from './ExecutionTypeIcon.svelte';
  import { subscribeExecutionEvents } from '$lib/execution-events';

  type ServiceHealth = {
    service: 'backend' | 'executor' | 'llm' | 'kafka';
    status: string;
    model: string | null;
    errorCode: string | null;
  };

  let { children }: { children: Snippet } = $props();
  let recentThreads = $state<ChatThread[]>([]);
  let chatTreePage = $state(0);
  let chatTreeLast = $state(false);
  let chatTreeLoading = $state(false);
  let chatTreeLoadingMore = $state(false);
  let executionTree = $state<Execution[]>([]);
  let resultTree = $state<Execution[]>([]);
  let executionTreePage = $state(0);
  let resultTreePage = $state(0);
  let executionTreeLast = $state(false);
  let resultTreeLast = $state(false);
  let executionTreeLoading = $state(false);
  let resultTreeLoading = $state(false);
  let executionTreeLoadingMore = $state(false);
  let resultTreeLoadingMore = $state(false);
  let serviceStatuses = $state<Record<string, ServiceHealth>>({
    backend: serviceHealth('backend', 'UNKNOWN'),
    executor: serviceHealth('executor', 'UNKNOWN'),
    llm: serviceHealth('llm', 'UNKNOWN'),
    kafka: serviceHealth('kafka', 'UNKNOWN')
  });
  let healthTimer: ReturnType<typeof setInterval> | undefined;
  let unsubscribeExecutionEvents: (() => void) | undefined;
  let systemTheme: MediaQueryList | undefined;
  let passwordDialogOpen = $state(false);
  let passwordEmailSending = $state(false);
  let passwordEmailSent = $state(false);
  let passwordEmailError = $state('');

  const main = [
    { href: '/chat', label: 'chat' as const, icon: MessageSquareText },
    { href: '/executions', label: 'executions' as const, icon: Activity },
    { href: '/results', label: 'results' as const, icon: LibraryBig },
    { href: '/entities', label: 'entities' as const, icon: Database }
  ];
  const admin = [
    { href: '/admin/users', label: 'users' as const, icon: Users }
  ];


  onMount(() => {
    systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    applySystemTheme(systemTheme);
    systemTheme.addEventListener('change', applySystemTheme);

    void (async () => {
      await Promise.all([
        loadChatTree(true),
        loadExecutionTree(true),
        loadResultTree(true)
      ]);
      await refreshServiceStatuses();
    })();
    healthTimer = setInterval(refreshServiceStatuses, 10_000);
    unsubscribeExecutionEvents = subscribeExecutionEvents((_event, name) => {
      if (name.startsWith('chat-thread-')) void refreshChatTreeHead();
      if (name.startsWith('execution-')) void refreshExecutionTreeHead();
      if (name.startsWith('entity-')) {
        window.dispatchEvent(new CustomEvent('kozmik:entity-changed', {
          detail: { entityId: _event.data, eventName: name }
        }));
      }
      if (['execution-result-ready', 'execution-failed'].includes(name)) {
        void refreshResultTreeHead();
      }
    });
    window.addEventListener('focus', refreshTrees);
    window.addEventListener('kozmik:execution-deleted', onExecutionDeleted);
    window.addEventListener('kozmik:chat-thread-deleted', onChatThreadDeleted);
    window.addEventListener('kozmik:chat-thread-renamed', onChatThreadRenamed);
    window.addEventListener('kozmik:chat-thread-created', onChatThreadCreated);
    return () => {
      if (healthTimer) clearInterval(healthTimer);
      unsubscribeExecutionEvents?.();
      window.removeEventListener('focus', refreshTrees);
      window.removeEventListener('kozmik:execution-deleted', onExecutionDeleted);
      window.removeEventListener('kozmik:chat-thread-deleted', onChatThreadDeleted);
      window.removeEventListener('kozmik:chat-thread-renamed', onChatThreadRenamed);
      window.removeEventListener('kozmik:chat-thread-created', onChatThreadCreated);
      systemTheme?.removeEventListener('change', applySystemTheme);
    };
  });

  function applySystemTheme(event: MediaQueryList | MediaQueryListEvent) {
    document.documentElement.classList.toggle('dark', event.matches);
  }

  async function loadChatTree(reset = false) {
    if (chatTreeLoading || (!reset && chatTreeLast)) return;
    chatTreeLoading = true;
    chatTreeLoadingMore = !reset;
    try {
      if (reset) {
        const pageCount = Math.max(chatTreePage + 1, 1);
        const responses = await Promise.all(
          Array.from({ length: pageCount }, (_, page) => api.threadPage(page, 5))
        );
        recentThreads = responses.flatMap((response) => response.items);
        const latestPage = responses.at(-1)!;
        chatTreePage = latestPage.page;
        chatTreeLast = latestPage.last;
      } else {
        const response = await api.threadPage(chatTreePage + 1, 5);
        recentThreads = [...recentThreads, ...response.items.filter(
          (item) => !recentThreads.some((existing) => existing.id === item.id)
        )];
        chatTreePage = response.page;
        chatTreeLast = response.last;
      }
    } catch {
      // Service status already communicates temporary backend unavailability.
    } finally {
      chatTreeLoading = false;
      chatTreeLoadingMore = false;
    }
  }

  function onChatTreeScroll(event: Event) {
    if (nearScrollEnd(event.currentTarget as HTMLElement)) {
      void loadChatTree();
    }
  }

  function onExecutionDeleted(event: Event) {
    const executionId = (event as CustomEvent<{ executionId: string }>).detail.executionId;
    executionTree = executionTree.filter((item) => item.id !== executionId);
    resultTree = resultTree.filter((item) => item.id !== executionId);
    void loadExecutionTree(true);
    void loadResultTree(true);
  }

  function onChatThreadDeleted(event: Event) {
    const threadId = (event as CustomEvent<{ threadId: string }>).detail.threadId;
    recentThreads = recentThreads.filter((item) => item.id !== threadId);
    void loadChatTree(true);
  }

  function onChatThreadRenamed(event: Event) {
    const thread = (event as CustomEvent<{ thread: ChatThread }>).detail?.thread;
    if (!thread) return;
    recentThreads = recentThreads.map((item) => item.id === thread.id ? thread : item);
  }

  function onChatThreadCreated(event: Event) {
    const thread = (event as CustomEvent<{ thread: ChatThread }>).detail?.thread;
    if (!thread) return;
    recentThreads = [thread, ...recentThreads.filter((item) => item.id !== thread.id)];
  }

  async function refreshChatTreeHead() {
    try {
      const response = await api.threadPage(0, 5);
      const headIds = new Set(response.items.map((item) => item.id));
      recentThreads = [
        ...response.items,
        ...recentThreads.filter((item) => !headIds.has(item.id))
      ];
      if (chatTreePage === 0) chatTreeLast = response.last;
    } catch {
      // The health indicator communicates temporary backend unavailability.
    }
  }

  async function refreshExecutionTreeHead() {
    try {
      const response = await api.executionPage({ page: 0, size: 5 });
      const headIds = new Set(response.items.map((item) => item.id));
      executionTree = [
        ...response.items,
        ...executionTree.filter((item) => !headIds.has(item.id))
      ];
      if (executionTreePage === 0) executionTreeLast = response.last;
    } catch {
      // The health indicator communicates temporary backend unavailability.
    }
  }

  async function refreshResultTreeHead() {
    try {
      const response = await api.executionPage({
        page: 0, size: 5, statuses: ['SUCCEEDED', 'FAILED']
      });
      const headIds = new Set(response.items.map((item) => item.id));
      resultTree = [
        ...response.items,
        ...resultTree.filter((item) => !headIds.has(item.id))
      ];
      if (resultTreePage === 0) resultTreeLast = response.last;
    } catch {
      // The health indicator communicates temporary backend unavailability.
    }
  }

  async function loadExecutionTree(reset = false) {
    if (executionTreeLoading || (!reset && executionTreeLast)) return;
    executionTreeLoading = true;
    executionTreeLoadingMore = !reset;
    try {
      if (reset) {
        const pageCount = Math.max(executionTreePage + 1, 1);
        const responses = await Promise.all(
          Array.from({ length: pageCount }, (_, page) =>
            api.executionPage({ page, size: 5 }))
        );
        executionTree = responses.flatMap((response) => response.items);
        const latestPage = responses.at(-1)!;
        executionTreePage = latestPage.page;
        executionTreeLast = latestPage.last;
        return;
      }
      const target = reset ? 0 : executionTreePage + 1;
      const response = await api.executionPage({ page: target, size: 5 });
      executionTree = [...executionTree, ...response.items.filter(
        (item) => !executionTree.some((existing) => existing.id === item.id))];
      executionTreePage = response.page;
      executionTreeLast = response.last;
    } catch {
      // The health indicator communicates temporary backend unavailability.
    } finally {
      executionTreeLoading = false;
      executionTreeLoadingMore = false;
    }
  }

  async function loadResultTree(reset = false) {
    if (resultTreeLoading || (!reset && resultTreeLast)) return;
    resultTreeLoading = true;
    resultTreeLoadingMore = !reset;
    try {
      if (reset) {
        const pageCount = Math.max(resultTreePage + 1, 1);
        const responses = await Promise.all(
          Array.from({ length: pageCount }, (_, page) =>
            api.executionPage({
              page, size: 5, statuses: ['SUCCEEDED', 'FAILED']
            }))
        );
        resultTree = responses.flatMap((response) => response.items);
        const latestPage = responses.at(-1)!;
        resultTreePage = latestPage.page;
        resultTreeLast = latestPage.last;
        return;
      }
      const target = reset ? 0 : resultTreePage + 1;
      const response = await api.executionPage({
        page: target, size: 5, statuses: ['SUCCEEDED', 'FAILED']
      });
      resultTree = [...resultTree, ...response.items.filter(
        (item) => !resultTree.some((existing) => existing.id === item.id))];
      resultTreePage = response.page;
      resultTreeLast = response.last;
    } catch {
      // The health indicator communicates temporary backend unavailability.
    } finally {
      resultTreeLoading = false;
      resultTreeLoadingMore = false;
    }
  }

  function refreshTrees() {
    void loadChatTree(true);
    void loadExecutionTree(true);
    void loadResultTree(true);
  }

  function nearScrollEnd(element: HTMLElement) {
    return element.scrollHeight - element.scrollTop - element.clientHeight <= 48;
  }

  function onExecutionTreeScroll(event: Event) {
    if (nearScrollEnd(event.currentTarget as HTMLElement)) {
      void loadExecutionTree();
    }
  }

  function onResultTreeScroll(event: Event) {
    if (nearScrollEnd(event.currentTarget as HTMLElement)) {
      void loadResultTree();
    }
  }

  async function refreshServiceStatuses() {
    try {
      const response = await api.serviceStatuses();
      serviceStatuses = Object.fromEntries(
        response.services.map((item) => [item.service, item])
      );
    } catch {
      serviceStatuses = {
        backend: serviceHealth('backend', 'UNAVAILABLE'),
        executor: serviceHealth('executor', 'UNKNOWN'),
        llm: serviceHealth('llm', 'UNKNOWN', 'EXECUTOR_UNAVAILABLE'),
        kafka: serviceHealth('kafka', 'UNKNOWN')
      };
    }
  }

  function serviceHealth(
    service: ServiceHealth['service'],
    status: string,
    errorCode: string | null = null
  ): ServiceHealth {
    return { service, status, model: null, errorCode };
  }

  function serviceStatus(service: string) {
    return serviceStatuses[service]?.status ?? 'UNKNOWN';
  }

  function serviceTooltip(service: string) {
    const health = serviceStatuses[service];
    if (service === 'llm') {
      if (available(health?.status ?? 'UNKNOWN') && health?.model) return health.model;
      if (health?.errorCode === 'LLM_MODEL_NOT_AVAILABLE') return $t('llmModelUnavailable');
      if (health?.errorCode === 'LLM_PROVIDER_AUTHENTICATION_FAILED') return $t('llmAuthenticationFailed');
      if (health?.errorCode === 'LLM_PROVIDER_ACCESS_DENIED') return $t('llmAccessDenied');
      if (health?.errorCode === 'LLM_PROVIDER_QUOTA_EXCEEDED') return $t('llmQuotaExceeded');
      if (health?.errorCode === 'EXECUTOR_UNAVAILABLE'
        || serviceStatus('executor') === 'UNAVAILABLE') return $t('llmHealthUnverified');
      if (health?.errorCode === 'LLM_PROVIDER_UNAVAILABLE') return $t('llmProviderUnavailable');
      return $t('serviceUnavailable');
    }
    return available(health?.status ?? 'UNKNOWN')
      ? statusLabel(health?.status ?? 'UNKNOWN', $locale)
      : $t('serviceUnavailable');
  }

  function available(status: string) {
    return ['UP', 'AVAILABLE'].includes(status.toUpperCase());
  }

  function liveConnectionActive() {
    return available(serviceStatus('kafka'));
  }

  function active(href: string) {
    return $page.url.pathname === href || $page.url.pathname.startsWith(`${href}/`);
  }

  async function logout() {
    await api.logout();
  }

  async function requestPasswordChange() {
    passwordDialogOpen = true;
    passwordEmailSending = true;
    passwordEmailSent = false;
    passwordEmailError = '';
    try {
      await api.requestPasswordChange();
      passwordEmailSent = true;
    } catch {
      passwordEmailError = $t('apiUnavailable');
    } finally {
      passwordEmailSending = false;
    }
  }
</script>

<a class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:shadow-md" href="#main-content">{$t('skip')}</a>
<Sidebar.Provider>
  <Sidebar.Root collapsible="icon">
    <Sidebar.Header>
      <Sidebar.Menu>
        <Sidebar.MenuItem>
          <Sidebar.MenuButton
            size="lg"
            class="h-auto px-2 py-2"
            aria-label={$t('brand')}
            tooltipContent={$t('brand')}
          >
            <img
              src="/favicon.svg"
              alt=""
              aria-hidden="true"
              class="mx-auto hidden size-5 shrink-0 group-data-[collapsible=icon]:block"
            />
            <span class="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
              <span class="truncate font-semibold">{$t('brand')}</span>
              <span class="truncate text-xs">Governed analytics</span>
            </span>
          </Sidebar.MenuButton>
        </Sidebar.MenuItem>
      </Sidebar.Menu>
    </Sidebar.Header>
    <Sidebar.Content>
      <Sidebar.Group>
        <Sidebar.GroupContent>
          <Sidebar.Menu>
            {#each main as item}
              {@const Icon = item.icon}
              <Sidebar.MenuItem>
                <Sidebar.MenuButton isActive={active(item.href)} tooltipContent={$t(item.label)}>
                  {#snippet child({ props })}
                    <a href={item.href} {...props}><Icon aria-hidden="true" /><span>{$t(item.label)}</span></a>
                  {/snippet}
                </Sidebar.MenuButton>
                {#if item.label === 'executions' && executionTree.length}
                  <Sidebar.MenuSub
                    class="max-h-36 overflow-y-auto overscroll-contain"
                    onscroll={onExecutionTreeScroll}
                    aria-label={$t('executions')}
                  >
                    {#each executionTree as execution (execution.id)}
                      {@const executionEntityName = $locale === 'tr' ? execution.entityNameTr || execution.entityName || execution.entityId : execution.entityName || execution.entityId}
                      {@const executionTitle = execution.originalRequest ?? `${execution.executionType} · ${executionEntityName}`}
                      {@const deletionPending = $deletingExecutionIds.has(execution.id)}
                      <Sidebar.MenuSubItem>
                        <Tooltip.Provider>
                          <Tooltip.Root>
                            <Tooltip.Trigger>
                              {#snippet child({ props })}
                                <Sidebar.MenuSubButton
                                  {...props}
                                  href={deletionPending ? undefined : `/executions/${execution.id}`}
                                  aria-disabled={deletionPending}
                                  tabindex={deletionPending ? -1 : undefined}
                                  isActive={$page.url.pathname === `/executions/${execution.id}`}
                                >
                                  <ExecutionTypeIcon
                                    kind={execution.executionType}
                                    status={execution.status}
                                    context="execution"
                                  />
                                  <span>{executionTitle}</span>
                                </Sidebar.MenuSubButton>
                              {/snippet}
                            </Tooltip.Trigger>
                            <Tooltip.Content
                              side="left"
                              sideOffset={8}
                              class="max-w-sm whitespace-normal"
                            >
                              {executionTitle} · {deletionPending ? $t('deleting') : execution.status}
                            </Tooltip.Content>
                          </Tooltip.Root>
                        </Tooltip.Provider>
                      </Sidebar.MenuSubItem>
                    {/each}
                    {#if executionTreeLoadingMore}
                      <li class="px-2 py-1 text-xs text-muted-foreground" aria-live="polite">
                        {$t('loading')}
                      </li>
                    {/if}
                  </Sidebar.MenuSub>
                {/if}
                {#if item.label === 'results' && resultTree.length}
                  <Sidebar.MenuSub
                    class="max-h-36 overflow-y-auto overscroll-contain"
                    onscroll={onResultTreeScroll}
                    aria-label={$t('results')}
                  >
                    {#each resultTree as result (result.id)}
                      {@const resultTitle = result.originalRequest ?? `${result.executionType} · ${result.entityName ?? result.entityId}`}
                      {@const deletionPending = $deletingExecutionIds.has(result.id)}
                      <Sidebar.MenuSubItem>
                        <Tooltip.Provider>
                          <Tooltip.Root>
                            <Tooltip.Trigger>
                              {#snippet child({ props })}
                                <Sidebar.MenuSubButton
                                  {...props}
                                  href={deletionPending ? undefined : `/results/${result.id}`}
                                  aria-disabled={deletionPending}
                                  tabindex={deletionPending ? -1 : undefined}
                                  isActive={$page.url.pathname === `/results/${result.id}`}
                                >
                                  <ExecutionTypeIcon
                                    kind={result.executionType}
                                    status={result.status}
                                    context="result"
                                  />
                                  <span>{resultTitle}</span>
                                </Sidebar.MenuSubButton>
                              {/snippet}
                            </Tooltip.Trigger>
                            <Tooltip.Content side="left" sideOffset={8} class="max-w-sm whitespace-normal">
                              {resultTitle} · {deletionPending ? $t('deleting') : result.status}
                            </Tooltip.Content>
                          </Tooltip.Root>
                        </Tooltip.Provider>
                      </Sidebar.MenuSubItem>
                    {/each}
                    {#if resultTreeLoadingMore}
                      <li class="px-2 py-1 text-xs text-muted-foreground" aria-live="polite">
                        {$t('loading')}
                      </li>
                    {/if}
                  </Sidebar.MenuSub>
                {/if}
              </Sidebar.MenuItem>
            {/each}
          </Sidebar.Menu>
        </Sidebar.GroupContent>
      </Sidebar.Group>
      {#if recentThreads.length}
        <Sidebar.Group>
          <Sidebar.GroupLabel>{$t('recentThreads')}</Sidebar.GroupLabel>
          <Sidebar.GroupContent>
            <Sidebar.Menu
              class="max-h-36 overflow-y-auto overscroll-contain"
              onscroll={onChatTreeScroll}
              aria-label={$t('recentThreads')}
            >
              {#each recentThreads as thread (thread.id)}
                <Sidebar.MenuItem>
                  <Tooltip.Provider>
                    <Tooltip.Root>
                      <Tooltip.Trigger>
                        {#snippet child({ props })}
                          <Sidebar.MenuButton>
                            {#snippet child({ props: menuProps })}
                              <a href={`/chat?thread=${thread.id}`} {...menuProps} {...props}>
                                <MessageSquareText />
                                <span class="min-w-0 truncate">{thread.title}</span>
                              </a>
                            {/snippet}
                          </Sidebar.MenuButton>
                        {/snippet}
                      </Tooltip.Trigger>
                      <Tooltip.Content side="right" sideOffset={8} class="max-w-sm whitespace-normal">
                        {thread.title}
                      </Tooltip.Content>
                    </Tooltip.Root>
                  </Tooltip.Provider>
                </Sidebar.MenuItem>
              {/each}
              {#if chatTreeLoadingMore}
                <li class="px-2 py-1 text-xs text-muted-foreground" aria-live="polite">
                  {$t('loading')}
                </li>
              {/if}
            </Sidebar.Menu>
          </Sidebar.GroupContent>
        </Sidebar.Group>
      {/if}
      {#if hasRole($currentUser, 'ADMIN')}
        <Sidebar.Group>
          <Sidebar.GroupLabel>{$t('administration')}</Sidebar.GroupLabel>
          <Sidebar.GroupContent>
            <Sidebar.Menu>
              {#each admin as item}
                {@const Icon = item.icon}
                <Sidebar.MenuItem>
                  <Sidebar.MenuButton isActive={active(item.href)} tooltipContent={$t(item.label)}>
                    {#snippet child({ props })}
                      <a href={item.href} {...props}><Icon /><span>{$t(item.label)}</span></a>
                    {/snippet}
                  </Sidebar.MenuButton>
                </Sidebar.MenuItem>
              {/each}
            </Sidebar.Menu>
          </Sidebar.GroupContent>
        </Sidebar.Group>
      {/if}
    </Sidebar.Content>
    <Sidebar.Footer>
      <Sidebar.Menu>
        <Sidebar.MenuItem>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger>
              {#snippet child({ props })}
                <Sidebar.MenuButton
                  {...props}
                  size="lg"
                  class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <Avatar.Root class="size-8 rounded-lg">
                    <Avatar.Fallback class="rounded-lg">
                      {($currentUser?.displayName || $currentUser?.username || '?').slice(0, 1).toUpperCase()}
                    </Avatar.Fallback>
                  </Avatar.Root>
                  <span class="grid flex-1 text-left text-sm leading-tight">
                    <span class="truncate font-medium">{$currentUser?.displayName || $currentUser?.username}</span>
                    <Tooltip.Provider>
                      <Tooltip.Root>
                        <Tooltip.Trigger>
                          {#snippet child({ props })}
                            <span {...props} class="truncate text-xs">{primaryRole($currentUser) ?? '—'}</span>
                          {/snippet}
                        </Tooltip.Trigger>
                        <Tooltip.Content side="right" sideOffset={8} class="max-w-sm whitespace-normal">
                          {primaryRole($currentUser) ?? '—'}
                        </Tooltip.Content>
                      </Tooltip.Root>
                    </Tooltip.Provider>
                  </span>
                  <ChevronsUpDown class="ml-auto size-4" />
                </Sidebar.MenuButton>
              {/snippet}
            </DropdownMenu.Trigger>
            <DropdownMenu.Content
              side="top"
              align="end"
              class="w-(--bits-dropdown-menu-anchor-width)"
            >
              <DropdownMenu.Item onclick={() => void requestPasswordChange()}>
                <KeyRound size={16} /> {$t('changePassword')}
              </DropdownMenu.Item>
              <DropdownMenu.Separator />
              <DropdownMenu.Item onclick={() => void logout()}>
                <LogOut size={16} /> {$t('signOut')}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </Sidebar.MenuItem>
      </Sidebar.Menu>
    </Sidebar.Footer>
    <Sidebar.Rail />
  </Sidebar.Root>
  <Sidebar.Inset class="h-svh min-h-0 min-w-0 overflow-hidden">
    <header class="flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <Sidebar.Trigger aria-label={$t('menu')} />
      <Sidebar.Separator orientation="vertical" class="mr-2 h-4" />
      <Tooltip.Provider>
        <div class="flex items-center gap-2" aria-label={$t('services')} aria-live="polite">
          {#each [
            ['backend', 'Backend'],
            ['executor', 'Executor'],
            ['llm', 'LLM']
          ] as service}
            <Tooltip.Root>
              <Tooltip.Trigger>
                {#snippet child({ props })}
                  <Badge
                    {...props}
                    variant="outline"
                    class={available(serviceStatus(service[0]))
                      ? 'gap-1.5 text-emerald-700 dark:text-emerald-400' : 'gap-1.5 text-destructive'}
                  >
                    <span class={`size-1.5 rounded-full ${available(serviceStatus(service[0])) ? 'bg-emerald-500' : 'bg-destructive'}`}></span>{service[1]}
                  </Badge>
                {/snippet}
              </Tooltip.Trigger>
              <Tooltip.Content>
                {serviceTooltip(service[0])}
              </Tooltip.Content>
            </Tooltip.Root>
          {/each}
        </div>
      </Tooltip.Provider>
      <div class="ml-auto flex items-center gap-1">
        <Tooltip.Provider>
          <Tooltip.Root>
            <Tooltip.Trigger>
              {#snippet child({ props })}
                <Badge
                  {...props}
                  variant="outline"
                  class={liveConnectionActive()
                    ? 'gap-1.5 text-emerald-700 dark:text-emerald-400'
                    : 'gap-1.5 text-destructive'}
                  aria-live="polite"
                >
                  <span class={`size-1.5 rounded-full ${liveConnectionActive() ? 'bg-emerald-500' : 'bg-destructive'}`}></span>
                  {liveConnectionActive() ? $t('streamLive') : $t('streamOffline')}
                </Badge>
              {/snippet}
            </Tooltip.Trigger>
            <Tooltip.Content side="bottom">{$t('streamDescription')}</Tooltip.Content>
          </Tooltip.Root>
        </Tooltip.Provider>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            {#snippet child({ props })}
              <Button {...props} variant="ghost" size="sm" aria-label={$t('language')}>
                <Languages size={17} aria-hidden="true" /> {$locale.toUpperCase()}
              </Button>
            {/snippet}
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end">
            <DropdownMenu.Item onclick={() => setLocale('tr')}>Türkçe</DropdownMenu.Item>
            <DropdownMenu.Item onclick={() => setLocale('en')}>English</DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </div>
    </header>
    <div class="pdf-navigation-tabs w-full min-w-0">
      <WorkspaceTabs />
    </div>
    <main id="main-content" tabindex="-1" class="workspace-content w-full min-h-0 min-w-0 max-w-screen-2xl flex-1 overflow-y-auto overscroll-contain p-4 md:p-6">{@render children()}</main>
  </Sidebar.Inset>
</Sidebar.Provider>

<Dialog.Root bind:open={passwordDialogOpen}>
  <Dialog.Content class="sm:max-w-md">
    <Dialog.Header>
      <Dialog.Title>{$t('changePassword')}</Dialog.Title>
      <Dialog.Description>
        {passwordEmailSent ? $t('passwordEmailSent') : $t('passwordEmailDescription')}
      </Dialog.Description>
    </Dialog.Header>
    {#if passwordEmailSending}
      <p class="text-sm text-muted-foreground" aria-live="polite">{$t('sending')}</p>
    {:else if passwordEmailError}
      <Alert.Root variant="destructive"><Alert.Description>{passwordEmailError}</Alert.Description></Alert.Root>
    {/if}
    <Dialog.Footer>
      <Button onclick={() => passwordDialogOpen = false}>{$t('close')}</Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

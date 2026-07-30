<script lang="ts">
  import { page } from '$app/stores';
  import {
    Activity,
    ChartNoAxesCombined,
    ChevronsUpDown,
    Database,
    Languages,
    KeyRound,
    LogOut,
    MessageSquareText,
    Moon,
    Sun,
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

  let { children }: { children: Snippet } = $props();
  let dark = $state(false);
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
  let serviceStatuses = $state<Record<string, string>>({
    backend: 'UNKNOWN',
    executor: 'UNKNOWN',
    llm: 'UNKNOWN',
    kafka: 'UNKNOWN'
  });
  let healthTimer: ReturnType<typeof setInterval> | undefined;
  let executionTimer: ReturnType<typeof setInterval> | undefined;
  let systemTheme: MediaQueryList | undefined;
  let passwordDialogOpen = $state(false);
  let passwordEmailSending = $state(false);
  let passwordEmailSent = $state(false);
  let passwordEmailError = $state('');

  const main = [
    { href: '/chat', label: 'chat' as const, icon: MessageSquareText },
    { href: '/executions', label: 'executions' as const, icon: Activity },
    { href: '/results', label: 'results' as const, icon: ChartNoAxesCombined },
    { href: '/entities', label: 'entities' as const, icon: Database }
  ];
  const admin = [
    { href: '/admin/users', label: 'users' as const, icon: Users }
  ];

  $effect(() => {
    dark = document.documentElement.classList.contains('dark');
  });

  onMount(() => {
    systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
    applyPreferredTheme();
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
    executionTimer = setInterval(refreshTrees, 5_000);
    window.addEventListener('focus', refreshTrees);
    window.addEventListener('kozmik:execution-deleted', onExecutionDeleted);
    window.addEventListener('kozmik:chat-thread-deleted', onChatThreadDeleted);
    return () => {
      if (healthTimer) clearInterval(healthTimer);
      if (executionTimer) clearInterval(executionTimer);
      window.removeEventListener('focus', refreshTrees);
      window.removeEventListener('kozmik:execution-deleted', onExecutionDeleted);
      window.removeEventListener('kozmik:chat-thread-deleted', onChatThreadDeleted);
      systemTheme?.removeEventListener('change', applySystemTheme);
    };
  });

  function applyPreferredTheme() {
    const preference = localStorage.getItem('kozmik-theme-preference');
    dark =
      preference === 'dark' ||
      ((preference !== 'light' && preference !== 'dark') && Boolean(systemTheme?.matches));
    document.documentElement.classList.toggle('dark', dark);
  }

  function applySystemTheme(event: MediaQueryListEvent) {
    const preference = localStorage.getItem('kozmik-theme-preference');
    if (preference === 'light' || preference === 'dark') return;
    dark = event.matches;
    document.documentElement.classList.toggle('dark', dark);
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
        response.services.map((item) => [item.service, item.status])
      );
    } catch {
      serviceStatuses = {
        backend: 'UNAVAILABLE',
        executor: 'UNKNOWN',
        llm: 'UNKNOWN',
        kafka: 'UNKNOWN'
      };
    }
  }

  function available(status: string) {
    return ['UP', 'AVAILABLE'].includes(status.toUpperCase());
  }

  function liveConnectionActive() {
    return available(serviceStatuses.kafka ?? 'UNKNOWN');
  }

  function toggleTheme() {
    dark = !dark;
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem('kozmik-theme-preference', dark ? 'dark' : 'light');
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
          <Sidebar.MenuButton size="lg" class="h-auto px-2 py-2">
            <span class="grid flex-1 text-left text-sm leading-tight">
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
                      {@const executionTitle = execution.originalRequest ?? `${execution.executionType} · ${execution.entityName ?? execution.entityId}`}
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
                  <Sidebar.MenuButton tooltipContent={thread.title}>
                    {#snippet child({ props })}
                      <a href={`/chat?thread=${thread.id}`} {...props}><MessageSquareText /><span>{thread.title}</span></a>
                    {/snippet}
                  </Sidebar.MenuButton>
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
  <Sidebar.Inset class="min-w-0 overflow-x-hidden">
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
                    class={available(serviceStatuses[service[0]] ?? 'UNKNOWN')
                      ? 'gap-1.5 text-emerald-700 dark:text-emerald-400' : 'gap-1.5 text-destructive'}
                  >
                    <span class={`size-1.5 rounded-full ${available(serviceStatuses[service[0]] ?? 'UNKNOWN') ? 'bg-emerald-500' : 'bg-destructive'}`}></span>{service[1]}
                  </Badge>
                {/snippet}
              </Tooltip.Trigger>
              <Tooltip.Content>
                {statusLabel(serviceStatuses[service[0]] ?? 'UNKNOWN', $locale)}
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
                  variant={liveConnectionActive() ? 'outline' : 'destructive'}
                  class={liveConnectionActive() ? 'gap-1.5 text-emerald-700 dark:text-emerald-400' : 'gap-1.5'}
                  aria-live="polite"
                >
                  <span class={`size-1.5 rounded-full ${liveConnectionActive() ? 'bg-emerald-500' : 'bg-destructive-foreground'}`}></span>
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
        <Button variant="ghost" size="icon" aria-label={$t('theme')} onclick={toggleTheme}>
          {#if dark}<Sun size={18} />{:else}<Moon size={18} />{/if}
        </Button>
      </div>
    </header>
    <div class="pdf-navigation-tabs w-full min-w-0">
      <WorkspaceTabs />
    </div>
    <main id="main-content" tabindex="-1" class="mx-auto w-full min-w-0 max-w-screen-2xl p-4 md:p-6">{@render children()}</main>
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

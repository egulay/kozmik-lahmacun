<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { page } from '$app/stores';
  import { Bot, MessageCirclePlus, Send, ShieldCheck, Trash2 } from '@lucide/svelte';
  import { api } from '$lib/api';
  import { locale, t } from '$lib/i18n';
  import type { ChatMessage, ChatThread } from '$lib/types';
  import { DurableEventStream } from '$lib/sse';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Card from '$lib/components/ui/card/index.js';
  import * as Alert from '$lib/components/ui/alert/index.js';
  import * as Avatar from '$lib/components/ui/avatar/index.js';
  import { ScrollArea } from '$lib/components/ui/scroll-area/index.js';
  import { chatConnection } from '$lib/chat-connection';
  import { linkExecutionReferences } from '$lib/chat-message';
  import { currentUser } from '$lib/session';
  import StateView from '$lib/components/StateView.svelte';
  import { Textarea } from '$lib/components/ui/textarea/index.js';
  import { Input } from '$lib/components/ui/input/index.js';
  import * as Dialog from '$lib/components/ui/dialog/index.js';

  let threads = $state<ChatThread[]>([]);
  let threadPage = $state(0);
  let threadLast = $state(false);
  let threadLoadingMore = $state(false);
  let threadViewport = $state<HTMLElement | null>(null);
  let messages = $state<ChatMessage[]>([]);
  let selected = $state<string | null>(null);
  let message = $state('');
  let loading = $state(true);
  let sending = $state(false);
  let error = $state('');
  let connected = $state(true);
  let stream: DurableEventStream | undefined;
  let liveMessage = $state<ChatMessage | null>(null);
  let createDialogOpen = $state(false);
  let deleteCandidate = $state<ChatThread | null>(null);
  let deletingThread = $state(false);
  let threadTitle = $state('');
  let messageEnd: HTMLDivElement;
  const draftPrefix = 'kozmik-chat-draft:';

  $effect(() => {
    const viewport = threadViewport;
    if (!viewport) return;
    const onscroll = () => {
      if (
        viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= 48
        && !threadLast
        && !threadLoadingMore
      ) {
        void loadThreads(false);
      }
    };
    viewport.addEventListener('scroll', onscroll, { passive: true });
    return () => viewport.removeEventListener('scroll', onscroll);
  });

  $effect(() => {
    const threadId = selected;
    const draft = message;
    if (!threadId || typeof sessionStorage === 'undefined') return;
    if (draft) {
      sessionStorage.setItem(`${draftPrefix}${threadId}`, draft);
    } else {
      sessionStorage.removeItem(`${draftPrefix}${threadId}`);
    }
  });

  onMount(() => {
    void loadThreads();
    return () => {
      persistDraft();
      stream?.close();
      chatConnection.set('idle');
    };
  });

  async function loadThreads(reset = true) {
    if (!reset && (threadLast || threadLoadingMore)) return;
    if (reset) loading = true;
    else threadLoadingMore = true;
    error = '';
    try {
      const response = await api.threadPage(reset ? 0 : threadPage + 1, 5);
      threads = reset
        ? response.items
        : [...threads, ...response.items.filter(
          (item) => !threads.some((existing) => existing.id === item.id)
        )];
      threadPage = response.page;
      threadLast = response.last;
      const requested = $page.url.searchParams.get('thread');
      if (reset && !selected && (requested || threads.length)) {
        await selectThread(requested ?? threads[0].id);
      }
    } catch {
      error = $t('apiUnavailable');
    } finally {
      if (reset) loading = false;
      threadLoadingMore = false;
    }
    await fillThreadList();
  }

  async function fillThreadList() {
    await tick();
    if (
      threadViewport
      && threadViewport.clientHeight > 0
      && threadViewport.scrollHeight <= threadViewport.clientHeight + 1
      && !threadLast
      && !threadLoadingMore
    ) {
      await loadThreads(false);
    }
  }

  async function selectThread(id: string) {
    persistDraft();
    selected = id;
    message = typeof sessionStorage === 'undefined'
      ? ''
      : sessionStorage.getItem(`${draftPrefix}${id}`) ?? '';
    stream?.close();
    liveMessage = null;
    try {
      messages = await api.messages(id);
      await scrollToLatest();
      const pending = [...messages].reverse().find((item) =>
        ['PENDING', 'STREAMING'].includes(item.status)
      );
      if (pending) connectStream(id, pending.id);
    } catch {
      error = $t('apiUnavailable');
    }
  }

  function persistDraft() {
    if (!selected || typeof sessionStorage === 'undefined') return;
    if (message) {
      sessionStorage.setItem(`${draftPrefix}${selected}`, message);
    } else {
      sessionStorage.removeItem(`${draftPrefix}${selected}`);
    }
  }

  async function createThread() {
    const title = threadTitle.trim();
    if (!title) return;
    try {
      const created = await api.createThread(title, $locale);
      threads = [created, ...threads];
      threadTitle = '';
      createDialogOpen = false;
      await selectThread(created.id);
    } catch {
      error = $t('apiUnavailable');
    }
  }

  async function deleteThread() {
    if (!deleteCandidate || deletingThread) return;
    deletingThread = true;
    error = '';
    try {
      const deletedId = deleteCandidate.id;
      await api.deleteThread(deletedId);
      if (typeof sessionStorage !== 'undefined') {
        sessionStorage.removeItem(`${draftPrefix}${deletedId}`);
      }
      if (selected === deletedId) {
        stream?.close();
        liveMessage = null;
        selected = null;
        messages = [];
        message = '';
      }
      window.dispatchEvent(new CustomEvent('kozmik:chat-thread-deleted', {
        detail: { threadId: deletedId }
      }));
      deleteCandidate = null;
      await loadThreads();
    } catch {
      error = $t('apiUnavailable');
    } finally {
      deletingThread = false;
    }
  }

  async function sendMessage() {
    const content = message.trim();
    if (!content || !selected || sending) return;
    const threadId = selected;
    sending = true;
    error = '';
    message = '';
    sessionStorage.removeItem(`${draftPrefix}${threadId}`);
    try {
      const posted = await api.postMessage(threadId, content, $locale);
      if (selected !== threadId) return;
      messages = [...messages, posted.userMessage, posted.assistantMessage];
      liveMessage = posted.assistantMessage;
      await scrollToLatest();
      connectStream(threadId, posted.assistantMessage.id);
    } catch {
      error = $t('apiUnavailable');
      if (selected === threadId && !message) message = content;
    } finally {
      sending = false;
    }
  }

  function connectStream(threadId: string, assistantMessageId: string) {
    stream?.close();
    stream = new DurableEventStream(
      `/api/chat/threads/${threadId}/stream?assistantMessageId=${encodeURIComponent(assistantMessageId)}`,
      {
        onConnectionChange: (value) => {
          connected = value;
          chatConnection.set(value ? 'connected' : 'disconnected');
        },
        onReconnect: () => reloadMessages(threadId),
        onEvent: async (event, name) => {
          let payload: Record<string, unknown> = {};
          try {
            payload = JSON.parse(event.data);
          } catch {
            // Invalid payloads are ignored and authoritative REST remains available.
          }
          const index = messages.findIndex((item) => item.id === assistantMessageId);
          if (index < 0) return;
          if (name === 'message-delta') {
            messages[index] = {
              ...messages[index],
              status: 'STREAMING',
              content: messages[index].content + String(payload.delta ?? '')
            };
            messages = [...messages];
            await scrollToLatest();
          }
          if (name === 'message-completed' || name === 'message-failed') {
            stream?.close();
            await reloadMessages(threadId);
          }
        }
      }
    );
    stream.connect();
  }

  async function reloadMessages(threadId: string) {
    try {
      messages = await api.messages(threadId);
      liveMessage = null;
      await scrollToLatest();
    } catch {
      connected = false;
    }
  }

  function onComposerKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  async function scrollToLatest() {
    await tick();
    messageEnd?.scrollIntoView({ block: 'end', behavior: 'auto' });
  }
</script>

<div class="grid h-[calc(100dvh-7rem)] min-h-[36rem] gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
  <Card.Root class="flex h-full min-h-0 flex-col overflow-hidden">
    <Card.Header class="flex flex-row items-center justify-between gap-2 pb-3">
      <Card.Title class="text-base">{$t('recentThreads')}</Card.Title>
      <Button size="icon" variant="outline" aria-label={$t('newThread')} onclick={() => (createDialogOpen = true)}>
        <MessageCirclePlus size={18} />
      </Button>
    </Card.Header>
    <Card.Content class="flex min-h-0 flex-1 flex-col">
      <StateView loading={loading && threads.length === 0} {error} empty={!loading && !error && threads.length === 0} emptyText={$t('noThreads')} onretry={loadThreads} />
      {#if threads.length}
        <ScrollArea class="min-h-0 flex-1" bind:viewportRef={threadViewport}>
          <div class="grid gap-1 pr-3" role="list">
            {#each threads as thread}
              <div class="group relative">
                <Button variant={selected === thread.id ? 'secondary' : 'ghost'}
                  class="h-auto w-full justify-start px-3 py-2 pr-10 text-left"
                  onclick={() => selectThread(thread.id)}
                  aria-current={selected === thread.id ? 'page' : undefined}>
                  <span class="grid min-w-0 gap-1">
                    <strong class="truncate">{thread.title}</strong>
                    <span class="text-xs font-normal text-muted-foreground">{new Date(thread.updatedAt).toLocaleDateString($locale)}</span>
                  </span>
                </Button>
                <Button type="button" size="icon-sm" variant="ghost"
                  class="absolute inset-y-0 right-1 my-auto opacity-0 transition-opacity active:!translate-y-0 group-hover:opacity-100 focus-visible:opacity-100"
                  aria-label={`${$t('deleteThread')}: ${thread.title}`}
                  onclick={(event) => { event.stopPropagation(); deleteCandidate = thread; }}>
                  <Trash2 size={15} />
                </Button>
              </div>
            {/each}
            {#if threadLoadingMore}
              <div class="px-3 py-2 text-xs text-muted-foreground" aria-live="polite">
                {$t('loading')}
              </div>
            {/if}
          </div>
        </ScrollArea>
      {/if}
    </Card.Content>
  </Card.Root>

  <Card.Root class="flex h-full min-h-0 min-w-0 flex-col overflow-hidden" aria-label={$t('chat')}>
    <Card.Header class="border-b">
      <Card.Title class="text-xl">{threads.find((item) => item.id === selected)?.title ?? $t('selectThread')}</Card.Title>
    </Card.Header>
    <Card.Content class="grid min-h-0 flex-1 grid-rows-[auto_minmax(0,1fr)] gap-6 overflow-hidden pt-2">
      <Alert.Root>
        <ShieldCheck />
        <Alert.Title>{$t('privacyTitle')}</Alert.Title>
        <Alert.Description>{$t('privacyBody')}</Alert.Description>
      </Alert.Root>
      <ScrollArea class="h-full min-h-0">
        <div class="flex min-h-full min-w-0 flex-col gap-4 px-1 pb-2 pr-5" aria-live="polite" aria-relevant="additions text">
          {#if !selected}
            <div class="m-auto grid justify-items-center gap-3 text-muted-foreground">
          <MessageCirclePlus size={36} aria-hidden="true" />
          <p>{$t('selectThread')}</p>
          <Button onclick={() => (createDialogOpen = true)}>{$t('createThread')}</Button>
            </div>
          {:else}
            {#each messages as item (item.id)}
              <div class={`flex min-w-0 gap-3 ${item.role === 'USER' ? 'flex-row-reverse' : ''}`}>
                <Avatar.Root class="size-8">
                  <Avatar.Fallback>
                    {#if item.role === 'USER'}
                      {($currentUser?.displayName || $currentUser?.username || '?').slice(0, 1).toUpperCase()}
                    {:else}
                      <Bot class="size-4" />
                    {/if}
                  </Avatar.Fallback>
                </Avatar.Root>
                <div class="relative w-fit min-w-0 max-w-[calc(100%_-_3rem)] shrink-0">
                  {#if item.role === 'ASSISTANT' && !item.content && ['PENDING', 'STREAMING'].includes(item.status)}
                    <span class="thinking-ring pointer-events-none absolute inset-0 rounded-xl border border-ring/70" aria-hidden="true"></span>
                  {/if}
                  <Card.Root class={`relative z-10 w-fit min-w-0 max-w-full shadow-none ${item.role === 'USER' ? 'bg-muted' : ''}`}>
                    <Card.Content class="px-3 py-2.5">
                      <p class="break-words whitespace-pre-wrap text-sm leading-5">
                        <span class="mr-1.5 font-medium text-muted-foreground">{item.role === 'USER' ? $t('you') : $t('brand')}:</span>{#if item.role === 'ASSISTANT' && !item.content && ['PENDING', 'STREAMING'].includes(item.status)}<span aria-label={$t('thinking')}>...</span>{:else}{#each linkExecutionReferences(item.content || (item.status === 'FAILED' ? $t('assistantFailed') : '...')) as part}{#if part.executionId}<a class="font-mono font-medium text-primary underline underline-offset-4 hover:text-primary/80" href={`/executions/${part.executionId}`}>{part.text}</a>{:else}{part.text}{/if}{/each}{/if}
                      </p>
                    </Card.Content>
                  </Card.Root>
                </div>
              </div>
            {/each}
          {/if}
          <div class="h-px shrink-0" bind:this={messageEnd} aria-hidden="true"></div>
        </div>
      </ScrollArea>
    </Card.Content>
    <Card.Footer class="border-t pt-4">
      <form class="flex w-full items-center gap-2" onsubmit={(event) => { event.preventDefault(); void sendMessage(); }}>
      <label class="sr-only" for="chat-message">{$t('messagePlaceholder')}</label>
      <Textarea
        id="chat-message"
        class="h-12 min-h-12 max-h-40 resize-none py-3"
        bind:value={message}
        rows={2}
        placeholder={$t('messagePlaceholder')}
        disabled={!selected}
        onkeydown={onComposerKeydown}
      />
      <Button class="h-12 min-w-28 shrink-0" type="submit" disabled={!selected || !message.trim() || sending} aria-label={$t('send')}>
        <Send size={17} /> {sending ? $t('sending') : $t('send')}
      </Button>
      </form>
    </Card.Footer>
  </Card.Root>
</div>

<Dialog.Root bind:open={createDialogOpen}>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>{$t('newThread')}</Dialog.Title>
      <Dialog.Description>{$t('threadTitle')}</Dialog.Description>
    </Dialog.Header>
    <form class="grid gap-4" onsubmit={(event) => { event.preventDefault(); void createThread(); }}>
      <Input bind:value={threadTitle} placeholder={$t('threadTitle')} autocomplete="off" />
      <Dialog.Footer>
        <Button type="submit" disabled={!threadTitle.trim()}>{$t('createThread')}</Button>
      </Dialog.Footer>
    </form>
  </Dialog.Content>
</Dialog.Root>

<style>
  .thinking-ring {
    animation: thinking-pulse 1.65s cubic-bezier(0.16, 1, 0.3, 1) infinite;
    box-shadow: 0 0 0 1px color-mix(in oklab, var(--ring) 30%, transparent);
    transform-origin: center;
  }

  @keyframes thinking-pulse {
    0% {
      opacity: 0.75;
      transform: scale(1);
    }
    75%,
    100% {
      opacity: 0;
      transform: scale(1.16, 1.45);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .thinking-ring {
      animation: none;
      opacity: 0.55;
      transform: scale(1.04, 1.12);
    }
  }
</style>

<Dialog.Root open={deleteCandidate !== null} onOpenChange={(open) => { if (!open && !deletingThread) deleteCandidate = null; }}>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>{$t('deleteThread')}</Dialog.Title>
      <Dialog.Description>
        {$t('deleteThreadConfirm').replace('{title}', deleteCandidate?.title ?? '')}
      </Dialog.Description>
    </Dialog.Header>
    <Dialog.Footer>
      <Button variant="outline" disabled={deletingThread} onclick={() => (deleteCandidate = null)}>
        {$t('cancel')}
      </Button>
      <Button variant="destructive" disabled={deletingThread} onclick={deleteThread}>
        {deletingThread ? $t('deleting') : $t('deleteThread')}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

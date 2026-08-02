<script lang="ts">
  import { onMount } from 'svelte';
  import { CircleAlert, KeyRound, MoreHorizontal, Pencil, Pause, Play, Plus, Search, Trash2 } from '@lucide/svelte';
  import { api } from '$lib/api';
  import type { ManagedUser, Role } from '$lib/types';
  import { locale, statusLabel, t } from '$lib/i18n';
  import { currentUser } from '$lib/session';
  import AdminGuard from '$lib/components/AdminGuard.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import { Input } from '$lib/components/ui/input/index.js';
  import { Badge } from '$lib/components/ui/badge/index.js';
  import * as Card from '$lib/components/ui/card/index.js';
  import * as Table from '$lib/components/ui/table/index.js';
  import * as Dialog from '$lib/components/ui/dialog/index.js';
  import * as DropdownMenu from '$lib/components/ui/dropdown-menu/index.js';
  import * as Tooltip from '$lib/components/ui/tooltip/index.js';
  import * as Select from '$lib/components/ui/select/index.js';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import StateView from '$lib/components/StateView.svelte';
  import ServerPagination from '$lib/components/ServerPagination.svelte';
  import { openWorkspaceTab } from '$lib/workspace-tabs';

  let users = $state<ManagedUser[]>([]);
  let loading = $state(true);
  let error = $state('');
  let page = $state(0);
  let size = $state(20);
  let totalElements = $state(0);
  let totalPages = $state(0);
  let selected = $state<ManagedUser | null>(null);
  let dialog = $state<'create' | 'edit' | 'reset' | 'suspend' | 'resume' | 'delete' | null>(null);
  let displayName = $state('');
  let email = $state('');
  let roles = $state<Role[]>([]);
  let saving = $state(false);
  let search = $state('');
  let status = $state('ALL');
  let searchTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => {
    openWorkspaceTab({
      pageId: 'users',
      title: $t('users'),
      tabType: 'page'
    });
    void load();
  });

  async function load(targetPage = page) {
    loading = true;
    try {
      const response = await api.adminUsers(
        targetPage, size, status === 'ALL' ? [] : [status], search
      );
      users = response.items;
      page = response.page;
      totalElements = response.totalElements;
      totalPages = response.totalPages;
      error = '';
    } catch { error = $t('apiUnavailable'); }
    finally { loading = false; }
  }

  function open(user: ManagedUser, action: typeof dialog) {
    selected = user;
    dialog = action;
    displayName = user.displayName;
    email = user.email;
    roles = [...user.roles];
  }

  function openCreate() {
    selected = null;
    dialog = 'create';
    displayName = '';
    email = '';
    roles = ['REPORTER'];
  }

  function selectRole(role: Role) {
    roles = [role];
  }

  function fullNameError() {
    const length = displayName.trim().length;
    if (length < 2) return $t('fullNameMinLength');
    if (length > 100) return $t('fullNameMaxLength');
    return '';
  }

  function emailError() {
    const value = email.trim();
    if (value.length > 254) return $t('emailMaxLength');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return $t('invalidEmail');
    return '';
  }

  function roleError() {
    return roles.length === 1 ? '' : $t('singleRoleRequired');
  }

  function formValid() {
    return !fullNameError() && !emailError() && !roleError();
  }

  async function apply() {
    if (!dialog) return;
    if ((dialog === 'create' || dialog === 'edit') && !formValid()) return;
    saving = true;
    try {
      if (dialog === 'create') {
        await api.createAdminUser({ displayName, email, roles });
      } else if (dialog === 'edit' && selected) {
        await api.updateAdminUser(selected.id, { displayName, email, roles });
      } else if (dialog === 'reset' && selected) {
        await api.resetAdminUserPassword(selected.id);
      } else if (dialog === 'suspend' && selected) {
        await api.suspendAdminUser(selected.id);
      } else if (dialog === 'resume' && selected) {
        await api.resumeAdminUser(selected.id);
      } else if (selected) {
        await api.deleteAdminUser(selected.id);
      }
      dialog = null;
      await load(page);
    } catch { error = $t('apiUnavailable'); }
    finally { saving = false; }
  }

  function changeSize(value: number) {
    size = value;
    void load(0);
  }

  function scheduleSearch() {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => void load(0), 300);
  }

  function changeStatus(value: string | undefined) {
    if (!value) return;
    status = value;
    void load(0);
  }

  function isCurrentUser(user: ManagedUser | null) {
    return Boolean(user && user.keycloakUserId === $currentUser?.userId);
  }
</script>

<AdminGuard>
  <div class="flex items-start justify-between gap-4">
    <PageHeader title={$t('users')} description={$t('usersBody')} />
    <Button onclick={openCreate}><Plus />{$t('addUser')}</Button>
  </div>
  <StateView loading={loading && users.length === 0} {error} empty={!loading && !error && users.length === 0} onretry={load} />
  <Card.Root>
    <Card.Content class="pt-6">
      <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:justify-between">
        <label class="relative w-full sm:max-w-sm">
          <span class="sr-only">{$t('search')}</span>
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={17} aria-hidden="true" />
          <Input bind:value={search} oninput={scheduleSearch} placeholder={$t('search')} class="pl-9" />
        </label>
        <label>
          <span class="sr-only">{$t('status')}</span>
          <Select.Root type="single" value={status} onValueChange={changeStatus}>
            <Select.Trigger class="w-[180px]">
              {status === 'ALL' ? $t('allStatuses') : statusLabel(status, $locale)}
            </Select.Trigger>
            <Select.Content>
              <Select.Item value="ALL">{$t('allStatuses')}</Select.Item>
              <Select.Item value="ACTIVE">{statusLabel('ACTIVE', $locale)}</Select.Item>
              <Select.Item value="SUSPENDED">{statusLabel('SUSPENDED', $locale)}</Select.Item>
            </Select.Content>
          </Select.Root>
        </label>
      </div>
      {#if users.length}
      <div
        class={`overflow-x-auto pt-6 transition-opacity duration-150 ${loading ? 'opacity-60' : ''}`}
        aria-busy={loading}
      >
        <Table.Root>
          <Table.Header><Table.Row>
            <Table.Head>{$t('fullName')}</Table.Head>
            <Table.Head>{$t('role')}</Table.Head><Table.Head>{$t('status')}</Table.Head>
            <Table.Head class="w-14 text-right">{$t('actions')}</Table.Head>
          </Table.Row></Table.Header>
          <Table.Body>
            {#each users as user}
              <Table.Row>
                <Table.Cell><div class="font-medium">{user.displayName}</div><div class="text-xs text-muted-foreground">{user.email}</div></Table.Cell>
                <Table.Cell><div class="flex flex-wrap gap-1">{#each user.roles as role}<Badge variant="outline">{role}</Badge>{/each}</div></Table.Cell>
                <Table.Cell><StatusBadge status={user.status} /></Table.Cell>
                <Table.Cell class="text-right">
                  <DropdownMenu.Root>
                    <DropdownMenu.Trigger>
                      {#snippet child({ props })}<Button {...props} variant="ghost" size="icon-sm" aria-label={$t('actions')}><MoreHorizontal /></Button>{/snippet}
                    </DropdownMenu.Trigger>
                    <DropdownMenu.Content align="end">
                      <DropdownMenu.Item onclick={() => open(user, 'edit')}><Pencil />{$t('editUser')}</DropdownMenu.Item>
                      <DropdownMenu.Item onclick={() => open(user, 'reset')}><KeyRound />{$t('resetPassword')}</DropdownMenu.Item>
                      {#if user.status === 'ACTIVE'}
                        <DropdownMenu.Item disabled={isCurrentUser(user)} onclick={() => open(user, 'suspend')}>
                          <Pause />{isCurrentUser(user) ? $t('cannotSuspendOwnUser') : $t('suspendUser')}
                        </DropdownMenu.Item>
                      {:else}
                        <DropdownMenu.Item onclick={() => open(user, 'resume')}><Play />{$t('resumeUser')}</DropdownMenu.Item>
                      {/if}
                      <DropdownMenu.Separator />
                      <DropdownMenu.Item variant="destructive" disabled={isCurrentUser(user)}
                        onclick={() => open(user, 'delete')}>
                        <Trash2 />{isCurrentUser(user) ? $t('cannotDeleteOwnUser') : $t('deleteUser')}
                      </DropdownMenu.Item>
                    </DropdownMenu.Content>
                  </DropdownMenu.Root>
                </Table.Cell>
              </Table.Row>
            {/each}
          </Table.Body>
        </Table.Root>
        <ServerPagination {page} {size} {totalElements} {totalPages}
          disabled={loading} onPage={(value) => load(value)} onSize={changeSize} />
      </div>
      {/if}
    </Card.Content>
  </Card.Root>
</AdminGuard>

<Dialog.Root open={dialog !== null} onOpenChange={(open) => { if (!open) dialog = null; }}>
  <Dialog.Content>
    <Dialog.Header>
      <Dialog.Title>{dialog === 'create' ? $t('addUser') : dialog === 'edit' ? $t('editUser') : dialog === 'reset' ? $t('resetPassword') : dialog === 'delete' ? $t('deleteUser') : dialog === 'suspend' ? $t('suspendUser') : $t('resumeUser')}</Dialog.Title>
      {#if dialog !== 'edit' && dialog !== 'create'}
        <Dialog.Description>{dialog === 'reset' ? $t('userResetPasswordConfirm') : dialog === 'delete' ? $t('userDeleteConfirm') : dialog === 'suspend' ? $t('userSuspendConfirm') : $t('userResumeConfirm')}</Dialog.Description>
      {/if}
    </Dialog.Header>
    {#if dialog === 'edit' || dialog === 'create'}
      <div class="grid gap-4">
        <label class="grid gap-2 text-sm">
          <span>{$t('fullName')}</span>
          <div class="relative">
            <Input bind:value={displayName} autocomplete="name" maxlength={100}
              aria-invalid={Boolean(fullNameError())} class="pr-9" />
            {#if fullNameError()}
              <Tooltip.Provider>
                <Tooltip.Root>
                  <Tooltip.Trigger>
                    {#snippet child({ props })}
                      <button {...props} type="button" aria-label={fullNameError()}
                        class="absolute right-2 top-1/2 -translate-y-1/2 text-destructive">
                        <CircleAlert size={16} />
                      </button>
                    {/snippet}
                  </Tooltip.Trigger>
                  <Tooltip.Content side="left">{fullNameError()}</Tooltip.Content>
                </Tooltip.Root>
              </Tooltip.Provider>
            {/if}
          </div>
        </label>
        <label class="grid gap-2 text-sm">
          <span>{$t('email')}</span>
          <div class="relative">
            <Input type="email" bind:value={email} autocomplete="email" maxlength={254}
              aria-invalid={Boolean(emailError())} class="pr-9" />
            {#if emailError()}
              <Tooltip.Provider>
                <Tooltip.Root>
                  <Tooltip.Trigger>
                    {#snippet child({ props })}
                      <button {...props} type="button" aria-label={emailError()}
                        class="absolute right-2 top-1/2 -translate-y-1/2 text-destructive">
                        <CircleAlert size={16} />
                      </button>
                    {/snippet}
                  </Tooltip.Trigger>
                  <Tooltip.Content side="left">{emailError()}</Tooltip.Content>
                </Tooltip.Root>
              </Tooltip.Provider>
            {/if}
          </div>
        </label>
        {#if dialog === 'create'}<p class="text-xs text-muted-foreground">{$t('invitationEmailHelp')}</p>{/if}
        <div class="grid gap-2 text-sm"><span>{$t('role')}</span><div class="flex flex-wrap gap-2">
          {#each ['REPORTER', 'SCIENTIST', 'ADMIN'] as role}
            <Button type="button" size="sm" variant={roles.includes(role as Role) ? 'default' : 'outline'}
              disabled={dialog === 'edit' && isCurrentUser(selected) && role !== 'ADMIN'}
              aria-pressed={roles.includes(role as Role)} onclick={() => selectRole(role as Role)}>{role}</Button>
          {/each}
        </div></div>
      </div>
    {/if}
    <Dialog.Footer>
      <Button variant="outline" onclick={() => dialog = null}>{$t('cancel')}</Button>
      <Button variant={dialog === 'delete' ? 'destructive' : 'default'}
        disabled={saving || ((dialog === 'edit' || dialog === 'create') && !formValid())} onclick={apply}>
        {saving ? $t('saving') : dialog === 'delete' ? $t('deleteUser') : dialog === 'reset' ? $t('sendEmail') : $t('save')}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>

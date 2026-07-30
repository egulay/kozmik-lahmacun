<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';
	import { currentUser, sessionLoading } from '$lib/session';
	import { t } from '$lib/i18n';
	import {
		reconcileWorkspaceTabs,
		type WorkspaceTab
	} from '$lib/workspace-tabs';
	import AppShell from '$lib/components/AppShell.svelte';
	import { Button } from '$lib/components/ui/button/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Skeleton } from '$lib/components/ui/skeleton/index.js';

	let { children } = $props();
	let sessionError = $state('');

	onMount(async () => {
		try {
			await api.initializeCsrf();
			const user = await api.currentUser();
			await reconcileWorkspaceTabs(workspaceTabExists);
			currentUser.set(user);
		} catch(error) {
			if (error instanceof ApiError && error.status === 401) {
				api.beginLogin();
				return;
			}
			sessionError = $t('apiUnavailable');
		} finally {
			sessionLoading.set(false);
		}
	});

	async function workspaceTabExists(tab: WorkspaceTab) {
		try {
			if (tab.tabType === 'result') {
				await api.result(tab.executionId);
			} else {
				await api.execution(tab.executionId);
			}
			return true;
		} catch (error) {
			return !(error instanceof ApiError && [403, 404].includes(error.status));
		}
	}
</script>

<svelte:head>
	<title>Kozmik Lahmacun · Governed analytics</title>

	<meta
		name="description"
		content="Privacy-safe governed analytics for nontechnical teams"
	/>
</svelte:head>

{#if $sessionLoading}
	<div class="flex min-h-screen items-center justify-center p-6" aria-live="polite">
		<Card.Root class="w-full max-w-sm">
			<Card.Header class="items-center text-center">
				<Skeleton class="size-10 rounded-lg" />
				<Skeleton class="h-5 w-32" />
				<Skeleton class="h-4 w-48" />
			</Card.Header>
		</Card.Root>
	</div>
{:else if !$currentUser}
	<div class="flex min-h-screen items-center justify-center p-6" aria-live="polite">
		<Card.Root class="w-full max-w-sm">
			<Card.Header class="items-center text-center">
				{#if sessionError}
					<Card.Title>{$t('apiUnavailable')}</Card.Title>
					<Card.Description>{sessionError}</Card.Description>
					<Button onclick={() => window.location.reload()}>{$t('retry')}</Button>
				{:else}
					<Skeleton class="size-10 rounded-lg" />
					<Skeleton class="h-5 w-32" />
					<Skeleton class="h-4 w-48" />
				{/if}
			</Card.Header>
		</Card.Root>
	</div>
{:else}
	<AppShell>{@render children()}</AppShell>
{/if}

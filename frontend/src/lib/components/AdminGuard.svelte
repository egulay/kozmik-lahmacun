<script lang="ts">
  import type { Snippet } from 'svelte';
  import { currentUser, hasRole } from '$lib/session';
  import { t } from '$lib/i18n';
  import * as Alert from '$lib/components/ui/alert/index.js';
  let { children }: { children: Snippet } = $props();
</script>
{#if hasRole($currentUser, 'ADMIN')}{@render children()}{:else}<Alert.Root variant="destructive"><Alert.Description>{$t('forbidden')}</Alert.Description></Alert.Root>{/if}

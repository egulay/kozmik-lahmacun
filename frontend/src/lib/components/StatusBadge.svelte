<script lang="ts">
  import { locale, statusLabel } from '$lib/i18n.js';
  import { Badge } from './ui/badge/index.js';
  let { status }: { status: string } = $props();
  const normalizedStatus = $derived(status.trim().toUpperCase());
  const tone = $derived(
    ['COMPLETED', 'SUCCEEDED', 'AVAILABLE', 'ACTIVE', 'UP'].includes(normalizedStatus)
      ? 'success'
      : ['FAILED', 'UNAVAILABLE', 'DOWN', 'TIMED_OUT'].includes(normalizedStatus)
        ? 'danger'
        : ['DEGRADED', 'CANCELLED'].includes(normalizedStatus)
          ? 'warning'
          : 'info'
  );
</script>

<Badge
  variant={tone === 'danger' ? 'destructive' : tone === 'success' ? 'default' : 'secondary'}
  class="w-fit"
>{statusLabel(normalizedStatus, $locale)}</Badge>

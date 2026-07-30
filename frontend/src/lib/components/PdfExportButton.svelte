<script lang="ts">
  import { FileDown } from '@lucide/svelte';
  import { onDestroy } from 'svelte';
  import { currentUser, hasRole } from '$lib/session';
  import { t } from '$lib/i18n';
  import { Button } from '$lib/components/ui/button/index.js';

  let {
    documentId,
    documentType
  }: {
    documentId: string;
    documentType: 'execution' | 'result';
  } = $props();

  let exporting = $state(false);
  let cleanupExport: (() => void) | undefined;

  onDestroy(() => cleanupExport?.());

  async function exportPdf() {
    if (!hasRole($currentUser, 'ADMIN') || exporting) return;
    exporting = true;
    const previousTitle = document.title;
    const wasDark = document.documentElement.classList.contains('dark');
    let cleanupTimer: ReturnType<typeof setTimeout> | undefined;
    const cleanup = () => {
      if (cleanupTimer) window.clearTimeout(cleanupTimer);
      document.body.classList.remove('pdf-exporting');
      if (wasDark) document.documentElement.classList.add('dark');
      document.title = previousTitle;
      exporting = false;
      window.removeEventListener('afterprint', cleanup);
      cleanupExport = undefined;
    };
    cleanupExport = cleanup;

    document.title = `kozmik-lahmacun-${documentType}-${documentId}`;
    document.body.classList.add('pdf-exporting');
    if (wasDark) document.documentElement.classList.remove('dark');
    window.addEventListener('afterprint', cleanup, { once: true });
    cleanupTimer = window.setTimeout(cleanup, 120_000);

    await document.fonts.ready;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
    );
    window.print();
    if (cleanupTimer) window.clearTimeout(cleanupTimer);
    cleanupTimer = window.setTimeout(cleanup, 1_000);
  }
</script>

{#if hasRole($currentUser, 'ADMIN')}
  <Button
    class="pdf-export-control"
    variant="outline"
    size="sm"
    disabled={exporting}
    onclick={exportPdf}
  >
    <FileDown size={16} />
    {exporting ? $t('preparingPdf') : $t('exportPdf')}
  </Button>
{/if}

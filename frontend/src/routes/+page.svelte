<script lang="ts">
  import { goto } from '$app/navigation';
  import { onMount } from 'svelte';
  onMount(() => void goto('/chat', { replaceState: true }));
</script>

<p class="sr-only">Kozmik Lahmacun</p>

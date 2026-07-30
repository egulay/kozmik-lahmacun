<script lang="ts">
	import { Progress as ProgressPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		ref = $bindable(null),
		value = 0,
		class: className,
		...restProps
	}: ProgressPrimitive.RootProps = $props();
</script>

<ProgressPrimitive.Root
	bind:ref
	data-slot="progress"
	{value}
	class={cn("bg-primary/20 relative h-2 w-full overflow-hidden rounded-full", className)}
	{...restProps}
>
	<div
		data-slot="progress-indicator"
		class="bg-primary h-full w-full flex-1 transition-transform duration-300 ease-out"
		style={`transform: translateX(-${100 - Math.min(100, Math.max(0, value ?? 0))}%)`}
	></div>
</ProgressPrimitive.Root>

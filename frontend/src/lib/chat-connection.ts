import { writable } from "svelte/store";

export const chatConnection = writable<"idle" | "connected" | "disconnected">("idle");

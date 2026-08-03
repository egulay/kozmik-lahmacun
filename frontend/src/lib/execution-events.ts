import { DurableEventStream } from './sse';

type Listener = (event: MessageEvent, eventName: string) => void | Promise<void>;
const listeners = new Set<Listener>();
let stream: DurableEventStream | undefined;

export function subscribeExecutionEvents(listener: Listener): () => void {
  listeners.add(listener);
  if (!stream) {
    stream = new DurableEventStream('/api/executions/stream', {
      onReconnect: notifyReload,
      onEvent: (event, eventName) => {
        for (const current of listeners) void current(event, eventName);
      }
    });
    stream.connect();
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      stream?.close();
      stream = undefined;
    }
  };
}

function notifyReload() {
  const event = new MessageEvent('execution-reconnect');
  for (const listener of listeners) void listener(event, 'reconnect');
}

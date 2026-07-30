import { afterEach, describe, expect, it, vi } from 'vitest';
import { DurableEventStream } from './sse';

class FakeEventSource {
  static latest: FakeEventSource;
  listeners = new Map<string, Array<(event: MessageEvent) => void>>();
  onopen?: () => void;
  onerror?: () => void;
  closed = false;

  constructor(public url: string, public options: EventSourceInit) {
    FakeEventSource.latest = this;
  }
  addEventListener(name: string, listener: EventListenerOrEventListenerObject) {
    const callback = listener as (event: MessageEvent) => void;
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), callback]);
  }
  emit(name: string, id: string, data = '{}') {
    for (const listener of this.listeners.get(name) ?? []) {
      listener({ data, lastEventId: id } as MessageEvent);
    }
  }
  close() {
    this.closed = true;
  }
}

describe('DurableEventStream', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('deduplicates event IDs and reloads authoritative state before reconnecting', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('EventSource', FakeEventSource);
    const eventHandler = vi.fn();
    const reload = vi.fn();
    const stream = new DurableEventStream('/api/executions/id/stream', {
      onEvent: eventHandler,
      onReconnect: reload
    });

    stream.connect();
    FakeEventSource.latest.emit('execution-status-changed', 'event-1');
    FakeEventSource.latest.emit('execution-status-changed', 'event-1');
    expect(eventHandler).toHaveBeenCalledTimes(1);

    FakeEventSource.latest.onerror?.();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(reload).toHaveBeenCalledTimes(1);
    stream.close();
  });
});

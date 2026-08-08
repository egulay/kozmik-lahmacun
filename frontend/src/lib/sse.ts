export interface StreamHandlers {
  onEvent: (event: MessageEvent, eventName: string) => void | Promise<void>;
  onReconnect: () => void | Promise<void>;
  onConnectionChange?: (connected: boolean) => void;
}

const eventNames = [
  'message-started',
  'message-delta',
  'message-completed',
  'message-failed',
  'chat-thread-created',
  'chat-thread-renamed',
  'chat-thread-updated',
  'chat-thread-deleted',
  'execution-created',
  'execution-status-changed',
  'execution-result-ready',
  'execution-failed',
  'ingestion-stage-changed',
  'ingestion-checkpoint',
  'ingestion-completed',
  'ingestion-failed',
  'entity-ingestion-changed',
  'heartbeat'
];

export class DurableEventStream {
  private source?: EventSource;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private attempts = 0;
  private stopped = false;
  private seen = new Set<string>();

  constructor(
    private readonly url: string,
    private readonly handlers: StreamHandlers
  ) {}

  connect() {
    this.stopped = false;
    this.open();
  }

  close() {
    this.stopped = true;
    this.source?.close();
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
  }

  private open() {
    if (this.stopped || typeof EventSource === 'undefined') return;
    this.source = new EventSource(this.url, { withCredentials: true });
    this.source.onopen = async () => {
      const wasReconnect = this.attempts > 0;
      this.attempts = 0;
      this.handlers.onConnectionChange?.(true);
      if (wasReconnect) await this.handlers.onReconnect();
    };
    for (const name of eventNames) {
      this.source.addEventListener(name, (raw) => {
        const event = raw as MessageEvent;
        const eventId = event.lastEventId;
        if (eventId && this.seen.has(eventId)) return;
        if (eventId) {
          this.seen.add(eventId);
          if (this.seen.size > 500) this.seen.delete(this.seen.values().next().value as string);
        }
        void this.handlers.onEvent(event, name);
      });
    }
    this.source.onerror = () => {
      this.source?.close();
      this.handlers.onConnectionChange?.(false);
      if (this.stopped) return;
      this.attempts += 1;
      const delay = Math.min(30_000, 1_000 * 2 ** Math.min(this.attempts - 1, 5));
      this.reconnectTimer = setTimeout(async () => {
        await this.handlers.onReconnect();
        this.open();
      }, delay);
    };
  }
}

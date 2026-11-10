import { assign } from "./assign.js";
import type {
  ApiResponse,
  ClientOptions,
  ExperimentConfig,
  Exposure,
  FlushResult,
  TrackedEvent,
} from "./types.js";

const KEY_PATTERN = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const EVENT_PATTERN = /^[a-z0-9_.:-]{1,64}$/;
const MAX_USER_ID = 128;

const DEFAULTS = {
  maxBatchSize: 100,
  maxQueueSize: 5000,
  flushIntervalMs: 5000,
  configTtlMs: 60_000,
} as const;

interface CachedConfig {
  readonly config: ExperimentConfig;
  readonly fetchedAt: number;
}

type SendOutcome = "ok" | "retry" | "drop";

/**
 * Assigns users locally (no network on the hot path once config is cached),
 * logs one exposure per user per experiment, and ships events in batches.
 * Every event carries a client-generated id, so retries are idempotent.
 */
export class SplitkitClient {
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;
  private readonly opts: Required<Omit<ClientOptions, "baseUrl" | "fetchFn">>;
  private configs: ReadonlyMap<string, CachedConfig> = new Map();
  private inflight: ReadonlyMap<string, Promise<ExperimentConfig | null>> = new Map();
  private exposed: ReadonlySet<string> = new Set();
  private exposures: readonly Exposure[] = [];
  private events: readonly TrackedEvent[] = [];
  private flushing: Promise<FlushResult> | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(options: ClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.fetchFn = options.fetchFn ?? globalThis.fetch.bind(globalThis);
    this.opts = {
      maxBatchSize: options.maxBatchSize ?? DEFAULTS.maxBatchSize,
      maxQueueSize: options.maxQueueSize ?? DEFAULTS.maxQueueSize,
      flushIntervalMs: options.flushIntervalMs ?? DEFAULTS.flushIntervalMs,
      configTtlMs: options.configTtlMs ?? DEFAULTS.configTtlMs,
      idFn: options.idFn ?? (() => globalThis.crypto.randomUUID()),
      now: options.now ?? (() => new Date()),
    };
    if (this.opts.flushIntervalMs > 0) {
      this.timer = setInterval(() => void this.flush(), this.opts.flushIntervalMs);
      (this.timer as { unref?: () => void }).unref?.();
    }
  }

  /** Variant for this user, or null if the experiment is unavailable or not running. */
  async getVariant(experimentKey: string, userId: string): Promise<string | null> {
    if (!KEY_PATTERN.test(experimentKey)) throw new Error(`invalid experiment key: ${experimentKey}`);
    validateUserId(userId);
    const config = await this.loadConfig(experimentKey);
    if (!config || config.status !== "running") return null;

    const variant = assign(config.variants, config.salt, userId);
    const marker = `${experimentKey}\u0000${userId}`;
    if (!this.exposed.has(marker)) {
      this.exposed = new Set([...this.exposed, marker]);
      this.exposures = bounded([...this.exposures, { experiment_key: experimentKey, user_id: userId, variant }], this.opts.maxQueueSize);
    }
    return variant;
  }

  track(userId: string, eventName: string, value?: number): void {
    validateUserId(userId);
    if (!EVENT_PATTERN.test(eventName)) throw new Error(`invalid event name: ${eventName}`);
    if (value !== undefined && !Number.isFinite(value)) throw new Error("event value must be a finite number");
    const event: TrackedEvent = {
      event_id: this.opts.idFn(),
      user_id: userId,
      event_name: eventName,
      value: value ?? null,
      ts: this.opts.now().toISOString(),
    };
    this.events = bounded([...this.events, event], this.opts.maxQueueSize);
  }

  pending(): number {
    return this.exposures.length + this.events.length;
  }

  /** Send everything queued. Concurrent calls share one in-flight flush. */
  flush(): Promise<FlushResult> {
    if (!this.flushing) {
      this.flushing = this.doFlush().finally(() => {
        this.flushing = null;
      });
    }
    return this.flushing;
  }

  close(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  private async doFlush(): Promise<FlushResult> {
    const exposures = this.exposures;
    const events = this.events;
    this.exposures = [];
    this.events = [];
    const ex = await this.sendAll("/v1/exposures", "exposures", exposures);
    const ev = await this.sendAll("/v1/events", "events", events);
    // failed items go back to the front of the queue, ahead of anything tracked meanwhile
    this.exposures = bounded([...ex.retry, ...this.exposures], this.opts.maxQueueSize);
    this.events = bounded([...ev.retry, ...this.events], this.opts.maxQueueSize);
    return {
      sent: ex.sent + ev.sent,
      failed: ex.retry.length + ev.retry.length,
      dropped: ex.dropped + ev.dropped,
    };
  }

  private async sendAll<T>(path: string, field: string, items: readonly T[]) {
    let sent = 0;
    let dropped = 0;
    let retry: readonly T[] = [];
    for (let i = 0; i < items.length; i += this.opts.maxBatchSize) {
      const batch = items.slice(i, i + this.opts.maxBatchSize);
      const outcome = await this.post(path, { [field]: batch });
      if (outcome === "ok") sent += batch.length;
      else if (outcome === "drop") dropped += batch.length;
      else retry = [...retry, ...batch];
    }
    return { sent, dropped, retry };
  }

  private async post(path: string, body: unknown): Promise<SendOutcome> {
    try {
      const res = await this.fetchFn(`${this.baseUrl}${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
        keepalive: true,
      });
      if (res.ok) return "ok";
      // 408/429 are transient; other 4xx mean the payload itself is bad
      if (res.status >= 500 || res.status === 408 || res.status === 429) return "retry";
      return "drop";
    } catch {
      return "retry";
    }
  }

  private loadConfig(key: string): Promise<ExperimentConfig | null> {
    const cached = this.configs.get(key);
    if (cached && Date.now() - cached.fetchedAt < this.opts.configTtlMs) {
      return Promise.resolve(cached.config);
    }
    const existing = this.inflight.get(key);
    if (existing) return existing;

    const request = this.fetchConfig(key).finally(() => {
      this.inflight = withoutKey(this.inflight, key);
    });
    this.inflight = new Map([...this.inflight, [key, request]]);
    return request;
  }

  private async fetchConfig(key: string): Promise<ExperimentConfig | null> {
    try {
      const res = await this.fetchFn(`${this.baseUrl}/v1/experiments/${encodeURIComponent(key)}/config`);
      if (!res.ok) return cachedOrNull(this.configs.get(key));
      const body = (await res.json()) as ApiResponse<ExperimentConfig>;
      if (!body.success || !body.data) return cachedOrNull(this.configs.get(key));
      this.configs = new Map([...this.configs, [key, { config: body.data, fetchedAt: Date.now() }]]);
      return body.data;
    } catch {
      // Fail open to the control experience: callers treat null as "show default".
      return cachedOrNull(this.configs.get(key));
    }
  }
}

function validateUserId(userId: string): void {
  if (!userId || userId.length > MAX_USER_ID) throw new Error("user id must be 1-128 characters");
}

function bounded<T>(items: readonly T[], max: number): readonly T[] {
  return items.length > max ? items.slice(items.length - max) : items;
}

function cachedOrNull(entry: CachedConfig | undefined): ExperimentConfig | null {
  return entry?.config ?? null;
}

function withoutKey<K, V>(map: ReadonlyMap<K, V>, key: K): ReadonlyMap<K, V> {
  return new Map([...map].filter(([k]) => k !== key));
}

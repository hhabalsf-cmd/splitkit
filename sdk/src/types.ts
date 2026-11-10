export interface Variant {
  readonly name: string;
  readonly weight: number;
}

export type ExperimentStatus = "draft" | "running" | "stopped";

export interface ExperimentConfig {
  readonly key: string;
  readonly salt: string;
  readonly status: ExperimentStatus;
  readonly variants: readonly Variant[];
}

export interface ApiResponse<T> {
  readonly success: boolean;
  readonly data: T | null;
  readonly error: string | null;
}

export interface Exposure {
  readonly experiment_key: string;
  readonly user_id: string;
  readonly variant: string;
}

export interface TrackedEvent {
  readonly event_id: string;
  readonly user_id: string;
  readonly event_name: string;
  readonly value: number | null;
  readonly ts: string;
}

export interface FlushResult {
  /** items the server acknowledged */
  readonly sent: number;
  /** items that hit a network/5xx error and were re-queued */
  readonly failed: number;
  /** items the server rejected as invalid (4xx) and were discarded */
  readonly dropped: number;
}

export interface ClientOptions {
  readonly baseUrl: string;
  readonly fetchFn?: typeof fetch;
  readonly maxBatchSize?: number;
  readonly maxQueueSize?: number;
  /** 0 disables the timer; call flush() yourself */
  readonly flushIntervalMs?: number;
  readonly configTtlMs?: number;
  readonly idFn?: () => string;
  readonly now?: () => Date;
}

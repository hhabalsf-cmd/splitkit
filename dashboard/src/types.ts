export type MetricType = "proportion" | "mean" | "ratio";
export type ExperimentStatus = "draft" | "running" | "stopped";

export interface Experiment {
  readonly key: string;
  readonly salt: string;
  readonly status: ExperimentStatus;
  readonly variants: readonly { readonly name: string; readonly weight: number }[];
  readonly metrics: readonly { readonly name: string; readonly type: MetricType; readonly description?: string }[];
  readonly created_at: string;
}

export interface MetricResult {
  readonly metric: string;
  readonly type: MetricType;
  readonly mean_a: number | null;
  readonly mean_b: number | null;
  readonly abs_lift: number | null;
  readonly rel_lift: number | null;
  readonly ci: readonly [number | null, number | null];
  readonly p_value: number;
  readonly adjusted_p: number;
  readonly significant: boolean;
  readonly sql: string;
}

export interface Readout {
  readonly experiment_key: string;
  readonly control: string;
  readonly treatment: string;
  readonly counts: Readonly<Record<string, number>>;
  readonly srm: { readonly p_value: number; readonly mismatch: boolean; readonly expected: readonly number[] };
  readonly blocked: boolean;
  readonly metrics: readonly MetricResult[];
}

export interface TimelinePoint {
  readonly as_of: string;
  readonly n_control: number;
  readonly n_treatment: number;
  readonly abs_lift: number | null;
  readonly ci_low: number | null;
  readonly ci_high: number | null;
  readonly p_value: number;
  readonly always_valid_p: number;
}

export interface Timeline {
  readonly metric: string;
  readonly type: MetricType;
  readonly points: readonly TimelinePoint[];
}

export interface Envelope<T> {
  readonly success: boolean;
  readonly data: T | null;
  readonly error: string | null;
}

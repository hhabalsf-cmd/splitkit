import type { MetricType } from "./types";

const MINUS = "−"; // typographic minus lines up with "+" in tabular figures
const EMPTY = "—";

const counts = new Intl.NumberFormat("en-US");

function signed(text: string, value: number): string {
  if (value > 0) return `+${text}`;
  if (value < 0) return `${MINUS}${text}`;
  return text;
}

export function formatValue(value: number | null, type: MetricType): string {
  if (value === null) return EMPTY;
  return type === "proportion" ? `${(value * 100).toFixed(2)}%` : value.toFixed(2);
}

/** Absolute lift: percentage points for proportions, raw units otherwise. */
export function formatLift(value: number | null, type: MetricType): string {
  if (value === null) return EMPTY;
  const magnitude = Math.abs(value);
  return type === "proportion"
    ? signed(`${(magnitude * 100).toFixed(2)} pts`, value)
    : signed(magnitude.toFixed(2), value);
}

export function formatRelative(value: number | null): string {
  if (value === null) return EMPTY;
  return signed(`${(Math.abs(value) * 100).toFixed(1)}%`, value);
}

export function formatP(p: number): string {
  return p < 0.001 ? "< 0.001" : p.toFixed(3);
}

export function formatCount(n: number): string {
  return counts.format(n);
}

export function formatDate(iso: string): string {
  const d = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

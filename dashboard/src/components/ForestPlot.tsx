import type { MetricResult } from "../types";
import { formatRelative } from "../format";

interface Row {
  readonly name: string;
  readonly lift: number;
  readonly low: number;
  readonly high: number;
  readonly tone: "ship" | "harm" | "neutral";
}

const ROW_H = 34;
const LABEL_W = 150;
const VALUE_W = 86;
const PLOT_W = 420;
const PAD = 14;

/** Relative lift (and CI) as a fraction of the control mean, so mixed units share one axis. */
export function toRows(metrics: readonly MetricResult[]): Row[] {
  return metrics.flatMap((m) => {
    const [lo, hi] = m.ci;
    if (!m.mean_a || m.abs_lift === null || lo === null || hi === null) return [];
    const base = Math.abs(m.mean_a);
    const tone = !m.significant ? "neutral" : m.abs_lift > 0 ? "ship" : "harm";
    return [{ name: m.metric, lift: m.abs_lift / base, low: lo / base, high: hi / base, tone }];
  });
}

export interface AxisDomain {
  readonly min: number;
  readonly max: number;
  readonly ticks: readonly number[];
}

/** 1-2-2.5-5 steps, roughly four intervals across the range. */
function niceStep(range: number): number {
  const raw = range / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const n = raw / magnitude;
  const factor = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return factor * magnitude;
}

/** Fit the intervals (always including zero, the "no effect" line) rather than mirroring around it. */
export function axisDomain(rows: readonly Row[]): AxisDomain {
  const lo = Math.min(0, ...rows.map((r) => r.low));
  const hi = Math.max(0, ...rows.map((r) => r.high));
  const step = niceStep(Math.max(hi - lo, 0.01));
  // nudge toward zero so values already on a step (e.g. lo = 0) don't round out a whole step
  const min = Math.floor(lo / step + 1e-9) * step;
  const max = Math.ceil(hi / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = min; v <= max + step / 2; v += step) ticks.push(Math.abs(v) < step / 1e6 ? 0 : v);
  return { min, max, ticks };
}

export function ForestPlot({ metrics }: { readonly metrics: readonly MetricResult[] }) {
  const rows = toRows(metrics);
  if (rows.length === 0) return <p className="muted">No metric has a usable baseline to plot yet.</p>;

  const { min, max, ticks } = axisDomain(rows);
  const x = (v: number) => LABEL_W + ((v - min) / (max - min)) * PLOT_W;
  const height = rows.length * ROW_H + PAD * 2 + 18;
  const width = LABEL_W + PLOT_W + VALUE_W;

  return (
    <svg className="forest" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Relative lift by metric with 95% confidence intervals">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={PAD} y2={height - 22} className={t === 0 ? "axis-zero" : "axis-grid"} />
          <text x={x(t)} y={height - 6} className="axis-label" textAnchor="middle">
            {t === 0 ? "0" : formatRelative(t)}
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const y = PAD + i * ROW_H + ROW_H / 2;
        return (
          <g key={r.name} className={`forest-row tone-${r.tone}`}>
            <text x={0} y={y + 4} className="forest-name">{r.name}</text>
            <line x1={x(r.low)} x2={x(r.high)} y1={y} y2={y} className="forest-ci" />
            <line x1={x(r.low)} x2={x(r.low)} y1={y - 5} y2={y + 5} className="forest-ci" />
            <line x1={x(r.high)} x2={x(r.high)} y1={y - 5} y2={y + 5} className="forest-ci" />
            <rect x={x(r.lift) - 4.5} y={y - 4.5} width={9} height={9} className="forest-point" />
            <text x={width} y={y + 4} className="forest-value" textAnchor="end">{formatRelative(r.lift)}</text>
          </g>
        );
      })}
    </svg>
  );
}

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDate, formatP } from "../format";
import type { Timeline } from "../types";

const FLOOR = 1e-12; // log axis can't show 0

const ticks = [1, 0.1, 0.01, 0.001, 0.0001];

export function SequentialChart({ timeline, alpha = 0.05 }: { readonly timeline: Timeline; readonly alpha?: number }) {
  if (timeline.points.length < 2) {
    return <p className="muted">Need at least two checkpoints with data in both arms.</p>;
  }
  const data = timeline.points.map((p) => ({
    t: formatDate(p.as_of),
    fixed: Math.max(p.p_value, FLOOR),
    valid: Math.max(p.always_valid_p, FLOOR),
    n: p.n_control + p.n_treatment,
  }));
  const lowest = Math.min(...data.flatMap((d) => [d.fixed, d.valid]));
  const domainMin = Math.min(1e-4, 10 ** Math.floor(Math.log10(lowest)));

  return (
    <div className="chart" role="img" aria-label="Fixed-horizon versus always-valid p-value over time">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--rule)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="t" tick={{ className: "axis-label" }} tickLine={false} axisLine={{ stroke: "var(--rule)" }} minTickGap={24} />
          <YAxis
            scale="log"
            domain={[domainMin, 1]}
            ticks={ticks.filter((t) => t >= domainMin)}
            tickFormatter={(v: number) => (v >= 0.01 ? String(v) : v.toExponential(0))}
            tick={{ className: "axis-label" }}
            tickLine={false}
            axisLine={false}
            width={52}
            allowDataOverflow
          />
          <ReferenceLine y={alpha} stroke="var(--accent)" strokeDasharray="4 3" label={{ value: `α = ${alpha}`, position: "insideBottomLeft", className: "axis-label" }} />
          <Tooltip
            formatter={(v: number, name: string) => [formatP(v), name]}
            labelFormatter={(label: string, payload) => {
              const n = payload?.[0]?.payload?.n as number | undefined;
              return n ? `${label} · ${n.toLocaleString()} users` : label;
            }}
            contentStyle={{ background: "var(--paper)", border: "1px solid var(--rule)", fontFamily: "var(--mono)", fontSize: 12 }}
          />
          <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
          <Line name="Fixed-horizon p (unsafe to peek)" dataKey="fixed" stroke="var(--muted)" strokeDasharray="5 4" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          <Line name="Always-valid p (mSPRT)" dataKey="valid" stroke="var(--ink)" dot={{ r: 2.5, fill: "var(--ink)" }} strokeWidth={2} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

import { formatLift, formatP, formatRelative, formatValue } from "../format";
import type { MetricResult } from "../types";

interface Props {
  readonly metrics: readonly MetricResult[];
  readonly control: string;
  readonly treatment: string;
}

export function MetricTable({ metrics, control, treatment }: Props) {
  return (
    <div className="table-wrap">
      <table className="metrics">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col" className="num">{control}</th>
            <th scope="col" className="num">{treatment}</th>
            <th scope="col" className="num">Lift</th>
            <th scope="col" className="num">95% CI</th>
            <th scope="col" className="num" title="Benjamini–Hochberg adjusted across this test's metrics">p (adj.)</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m, i) => {
            const tone = !m.significant ? "neutral" : (m.abs_lift ?? 0) > 0 ? "ship" : "harm";
            return (
              <tr key={m.metric} className={`tone-${tone}`}>
                <th scope="row">
                  {m.metric}
                  {i === 0 && <span className="tag">primary</span>}
                </th>
                <td className="num">{formatValue(m.mean_a, m.type)}</td>
                <td className="num">{formatValue(m.mean_b, m.type)}</td>
                <td className="num lift">
                  {formatLift(m.abs_lift, m.type)}
                  <span className="rel">{formatRelative(m.rel_lift)}</span>
                </td>
                <td className="num">
                  [{formatLift(m.ci[0], m.type)}, {formatLift(m.ci[1], m.type)}]
                </td>
                <td className="num">
                  {formatP(m.adjusted_p)}
                  {m.significant && <span className="sig" aria-label="significant">●</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function SqlPanel({ metrics }: { readonly metrics: readonly MetricResult[] }) {
  return (
    <div className="sql-list">
      {metrics.map((m) => (
        <details key={m.metric} className="sql">
          <summary>
            Show SQL for <code>{m.metric}</code>
          </summary>
          <pre>
            <code>{m.sql}</code>
          </pre>
        </details>
      ))}
    </div>
  );
}

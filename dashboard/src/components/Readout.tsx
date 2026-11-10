import { lazy, Suspense, useEffect, useState } from "react";
import { ApiError, type ApiClient } from "../api";
import { formatCount, formatP } from "../format";
import type { Readout as ReadoutData, Timeline } from "../types";
import { verdictFor } from "../verdict";
import { ForestPlot } from "./ForestPlot";
import { MetricTable, SqlPanel } from "./MetricTable";

// Recharts is most of the bundle and only this chart uses it: load it on demand.
const SequentialChart = lazy(() => import("./SequentialChart").then((m) => ({ default: m.SequentialChart })));

type State =
  | { readonly kind: "loading" }
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "ready"; readonly readout: ReadoutData; readonly timeline: Timeline | null };

interface Props {
  readonly api: ApiClient;
  readonly experimentKey: string;
  readonly onUnauthorized: () => void;
}

export function Readout({ api, experimentKey, onUnauthorized }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    (async () => {
      try {
        const readout = await api.results(experimentKey);
        const primary = readout.metrics[0]?.metric;
        // the timeline is a nice-to-have: a failure there shouldn't hide the readout
        const timeline = primary ? await api.timeline(experimentKey, primary).catch(() => null) : null;
        if (!cancelled) setState({ kind: "ready", readout, timeline });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) return onUnauthorized();
        setState({ kind: "error", message: err instanceof Error ? err.message : "Something went wrong." });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, experimentKey, onUnauthorized]);

  if (state.kind === "loading") return <p className="muted pad">Loading readout…</p>;
  if (state.kind === "error") {
    return (
      <section className="notice">
        <h2>Can't show this readout yet</h2>
        <p>{state.message}</p>
      </section>
    );
  }

  const { readout, timeline } = state;
  const verdict = verdictFor(readout);
  const total = Object.values(readout.counts).reduce((a, b) => a + b, 0);

  return (
    <article className="readout">
      <header className="readout-head reveal">
        <p className="eyebrow">Experiment readout</p>
        <h1>{readout.experiment_key}</h1>
        <p className="counts">
          {formatCount(total)} users ·{" "}
          {Object.entries(readout.counts).map(([arm, n], i) => (
            <span key={arm}>
              {i > 0 && " / "}
              {arm} {formatCount(n)}
            </span>
          ))}
        </p>
      </header>

      <section className={`verdict tone-${verdict.tone} reveal`} aria-live="polite">
        <h2>{verdict.headline}</h2>
        <p>{verdict.detail}</p>
      </section>

      <p className={`srm reveal ${readout.srm.mismatch ? "srm-fail" : ""}`}>
        <strong>Sample ratio check:</strong>{" "}
        {readout.srm.mismatch ? "failed" : "passed"} (χ² p = {formatP(readout.srm.p_value)}).{" "}
        {readout.srm.mismatch
          ? "Results are withheld from significance until the split is fixed."
          : "Assignment matches the planned split."}
      </p>

      <figure className="reveal">
        <div className="figure-scroll">
          <ForestPlot metrics={readout.metrics} />
        </div>
        <figcaption>
          <span className="fig">Fig. 1</span> Relative lift of {readout.treatment} over {readout.control}, with 95%
          confidence intervals. Filled marks are significant after Benjamini–Hochberg correction.
        </figcaption>
      </figure>

      <MetricTable metrics={readout.metrics} control={readout.control} treatment={readout.treatment} />

      {timeline && (
        <figure className="reveal">
          <Suspense fallback={<p className="muted">Drawing chart…</p>}>
            <SequentialChart timeline={timeline} />
          </Suspense>
          <figcaption>
            <span className="fig">Fig. 2</span> Checking a fixed-horizon p-value daily inflates false positives; the
            always-valid p-value for <code>{timeline.metric}</code> can be checked at any time.
          </figcaption>
        </figure>
      )}

      <SqlPanel metrics={readout.metrics} />
    </article>
  );
}

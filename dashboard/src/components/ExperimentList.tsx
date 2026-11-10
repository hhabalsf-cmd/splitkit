import { useEffect, useState } from "react";
import { ApiError, type ApiClient } from "../api";
import { formatDate } from "../format";
import type { Experiment } from "../types";

type State =
  | { readonly kind: "loading" }
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "ready"; readonly experiments: readonly Experiment[] };

interface Props {
  readonly api: ApiClient;
  readonly onUnauthorized: () => void;
}

export function ExperimentList({ api, onUnauthorized }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    api
      .listExperiments()
      .then((experiments) => !cancelled && setState({ kind: "ready", experiments }))
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) return onUnauthorized();
        setState({ kind: "error", message: err instanceof Error ? err.message : "Could not load experiments." });
      });
    return () => {
      cancelled = true;
    };
  }, [api, onUnauthorized]);

  if (state.kind === "loading") return <p className="muted pad">Loading experiments…</p>;
  if (state.kind === "error") return <p className="notice">{state.message}</p>;
  if (state.experiments.length === 0) {
    return (
      <section className="notice">
        <h2>No experiments yet</h2>
        <p>
          Create one with <code>POST /v1/experiments</code>, then start it to begin collecting exposures.
        </p>
      </section>
    );
  }

  return (
    <section>
      <header className="list-head reveal">
        <p className="eyebrow">Index</p>
        <h1>Experiments</h1>
      </header>
      <ol className="exp-list">
        {state.experiments.map((e, i) => (
          <li key={e.key} className="reveal" style={{ animationDelay: `${60 + i * 40}ms` }}>
            <a href={`#/exp/${encodeURIComponent(e.key)}`}>
              <span className="exp-key">{e.key}</span>
              <span className={`status status-${e.status}`}>{e.status}</span>
              <span className="exp-meta">
                {e.variants.map((v) => `${v.name} ${Math.round(v.weight * 100)}%`).join(" · ")}
              </span>
              <span className="exp-meta">
                {e.metrics.length} metric{e.metrics.length === 1 ? "" : "s"} · {formatDate(e.created_at)}
              </span>
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}

import type { Readout } from "./types";

export type VerdictTone = "ship" | "harm" | "neutral" | "warn";

export interface Verdict {
  readonly tone: VerdictTone;
  readonly headline: string;
  readonly detail: string;
}

/**
 * The decision a reader should take away, driven by the primary (first) metric.
 * Secondary metrics are guardrails to inspect, not tie-breakers.
 */
export function verdictFor(readout: Readout): Verdict {
  if (readout.blocked) {
    return {
      tone: "warn",
      headline: "Hold — sample ratio mismatch",
      detail:
        "Assignment counts don't match the planned split, so some users are being lost or " +
        "double-counted. Fix the exposure logging before trusting any metric below.",
    };
  }
  const primary = readout.metrics[0];
  if (!primary) {
    return { tone: "neutral", headline: "No metrics defined", detail: "Add a metric to analyze this test." };
  }
  if (!primary.significant) {
    return {
      tone: "neutral",
      headline: "No detectable difference",
      detail: `${primary.metric} hasn't moved beyond noise. Keep running if the test is under-powered, or call it.`,
    };
  }
  if ((primary.abs_lift ?? 0) > 0) {
    return {
      tone: "ship",
      headline: "Ship treatment",
      detail: `${primary.metric} improved and the result survives the multiple-testing correction.`,
    };
  }
  return {
    tone: "harm",
    headline: "Keep control",
    detail: `${primary.metric} got worse under treatment, and the drop survives the multiple-testing correction.`,
  };
}

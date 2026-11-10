import { describe, expect, it } from "vitest";
import { formatLift, formatP, formatValue, formatCount } from "../src/format";
import { verdictFor } from "../src/verdict";
import type { MetricResult, Readout } from "../src/types";

const metric = (over: Partial<MetricResult> = {}): MetricResult => ({
  metric: "purchase_rate",
  type: "proportion",
  mean_a: 0.1,
  mean_b: 0.12,
  abs_lift: 0.02,
  rel_lift: 0.2,
  ci: [0.01, 0.03],
  p_value: 0.001,
  adjusted_p: 0.002,
  significant: true,
  sql: "WITH clean_exposure AS (...)",
  ...over,
});

const readout = (over: Partial<Readout> = {}): Readout => ({
  experiment_key: "checkout-v2",
  control: "control",
  treatment: "treatment",
  counts: { control: 5000, treatment: 5010 },
  srm: { p_value: 0.9, mismatch: false, expected: [5005, 5005] },
  blocked: false,
  metrics: [metric()],
  ...over,
});

describe("format", () => {
  it("formats proportions as percentages and lifts as points", () => {
    expect(formatValue(0.1234, "proportion")).toBe("12.34%");
    expect(formatLift(0.0082, "proportion")).toBe("+0.82 pts");
    expect(formatLift(-0.0082, "proportion")).toBe("−0.82 pts");
  });

  it("formats means with sensible precision", () => {
    expect(formatValue(52.456, "mean")).toBe("52.46");
    expect(formatLift(-1.157, "mean")).toBe("−1.16");
  });

  it("formats p-values the way papers do", () => {
    expect(formatP(0.0412)).toBe("0.041");
    expect(formatP(0.00012)).toBe("< 0.001");
    expect(formatP(1)).toBe("1.000");
  });

  it("handles missing values and big counts", () => {
    expect(formatValue(null, "mean")).toBe("—");
    expect(formatLift(null, "proportion")).toBe("—");
    expect(formatCount(13979592)).toBe("13,979,592");
  });
});

describe("verdictFor", () => {
  it("holds when the sample ratio is off, regardless of metrics", () => {
    const v = verdictFor(readout({ blocked: true, srm: { p_value: 1e-6, mismatch: true, expected: [1, 1] } }));
    expect(v.tone).toBe("warn");
    expect(v.headline).toMatch(/hold/i);
  });

  it("recommends shipping on a significant positive primary metric", () => {
    expect(verdictFor(readout()).headline).toBe("Ship treatment");
  });

  it("recommends keeping control on a significant negative primary metric", () => {
    const v = verdictFor(readout({ metrics: [metric({ abs_lift: -0.01, ci: [-0.02, -0.005] })] }));
    expect(v.headline).toBe("Keep control");
    expect(v.tone).toBe("harm");
  });

  it("says so plainly when there is no detectable difference", () => {
    const v = verdictFor(readout({ metrics: [metric({ significant: false, adjusted_p: 0.4 })] }));
    expect(v.tone).toBe("neutral");
    expect(v.headline).toMatch(/no detectable difference/i);
  });

  it("only the primary (first) metric drives the verdict", () => {
    const v = verdictFor(readout({
      metrics: [metric({ significant: false }), metric({ metric: "revenue", significant: true })],
    }));
    expect(v.tone).toBe("neutral");
  });
});

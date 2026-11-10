import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient } from "../src/api";
import { toRows } from "../src/components/ForestPlot";
import { KeyGate } from "../src/components/KeyGate";
import { Readout } from "../src/components/Readout";
import type { MetricResult, Readout as ReadoutData, Timeline } from "../src/types";


const metric = (over: Partial<MetricResult> = {}): MetricResult => ({
  metric: "retention_7",
  type: "proportion",
  mean_a: 0.19,
  mean_b: 0.182,
  abs_lift: -0.0082,
  rel_lift: -0.043,
  ci: [-0.0133, -0.0031],
  p_value: 0.0016,
  adjusted_p: 0.0047,
  significant: true,
  sql: "WITH clean_exposure AS (SELECT 1)",
  ...over,
});

const READOUT: ReadoutData = {
  experiment_key: "cookie_cats",
  control: "gate_30",
  treatment: "gate_40",
  counts: { gate_30: 44700, gate_40: 45489 },
  srm: { p_value: 0.0086, mismatch: false, expected: [45094.5, 45094.5] },
  blocked: false,
  metrics: [metric(), metric({ metric: "game_rounds", type: "mean", mean_a: 52.46, mean_b: 51.3, abs_lift: -1.16, rel_lift: -0.022, ci: [-3.72, 1.4], significant: false, adjusted_p: 0.38 })],
};

const TIMELINE: Timeline = {
  metric: "retention_7",
  type: "proportion",
  points: [
    { as_of: "2024-01-02T00:00:00", n_control: 100, n_treatment: 100, abs_lift: -0.01, ci_low: -0.05, ci_high: 0.03, p_value: 0.3, always_valid_p: 1 },
    { as_of: "2024-01-03T00:00:00", n_control: 200, n_treatment: 200, abs_lift: -0.01, ci_low: -0.03, ci_high: 0.01, p_value: 0.04, always_valid_p: 0.4 },
  ],
};

function fakeApi(over: Partial<ApiClient> = {}): ApiClient {
  return {
    listExperiments: vi.fn(),
    results: vi.fn(async () => READOUT),
    timeline: vi.fn(async () => TIMELINE),
    ...over,
  } as unknown as ApiClient;
}

describe("Readout", () => {
  it("leads with the verdict and shows every metric", async () => {
    render(<Readout api={fakeApi()} experimentKey="cookie_cats" onUnauthorized={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Keep control" })).toBeInTheDocument();
    expect(screen.getByText(/90,189 users/)).toBeInTheDocument();
    expect(screen.getAllByText("retention_7").length).toBeGreaterThan(0);
    expect(screen.getByRole("cell", { name: "−0.82 pts −4.3%" })).toBeInTheDocument();
    expect(screen.getByText(/Sample ratio check:/).closest("p")).toHaveTextContent(/passed/);
  });

  it("still renders the readout when the timeline fails", async () => {
    const api = fakeApi({ timeline: vi.fn(async () => Promise.reject(new ApiError(500, "boom"))) as ApiClient["timeline"] });
    render(<Readout api={api} experimentKey="cookie_cats" onUnauthorized={vi.fn()} />);
    expect(await screen.findByRole("heading", { name: "Keep control" })).toBeInTheDocument();
    expect(screen.queryByText(/Fig. 2/)).not.toBeInTheDocument();
  });

  it("explains a not-enough-data error instead of crashing", async () => {
    const api = fakeApi({ results: vi.fn(async () => Promise.reject(new ApiError(409, "not enough data to analyze yet"))) as ApiClient["results"] });
    render(<Readout api={api} experimentKey="new-exp" onUnauthorized={vi.fn()} />);
    expect(await screen.findByText("not enough data to analyze yet")).toBeInTheDocument();
  });

  it("hands 401s back to the app", async () => {
    const onUnauthorized = vi.fn();
    const api = fakeApi({ results: vi.fn(async () => Promise.reject(new ApiError(401, "nope"))) as ApiClient["results"] });
    render(<Readout api={api} experimentKey="x" onUnauthorized={onUnauthorized} />);
    await waitFor(() => expect(onUnauthorized).toHaveBeenCalled());
  });
});

describe("ForestPlot rows", () => {
  it("scales lifts by the control mean and drops rows without a baseline", () => {
    const rows = toRows([metric(), metric({ metric: "zero_base", mean_a: 0 })]);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.lift).toBeCloseTo(-0.0082 / 0.19);
    expect(rows[0]!.tone).toBe("harm");
  });
});

describe("KeyGate", () => {
  it("rejects short keys before calling the server", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<KeyGate onUnlock={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Admin key"), { target: { value: "short-key" } });
    expect(screen.getByLabelText("Admin key")).toHaveValue("short-key");
    fireEvent.click(screen.getByRole("button", { name: "Open readouts" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 16/);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe("ForestPlot axis", () => {
  it("fits the data instead of mirroring around zero", async () => {
    const { axisDomain } = await import("../src/components/ForestPlot");
    const allPositive = axisDomain([{ name: "a", lift: 0.13, low: 0.05, high: 0.22, tone: "ship" }]);
    expect(allPositive.min).toBe(0);
    expect(allPositive.max).toBeGreaterThanOrEqual(0.22);
    expect(allPositive.max).toBeLessThan(0.4);
    expect(allPositive.ticks).toContain(0);
  });

  it("always includes zero and spans both signs when needed", async () => {
    const { axisDomain } = await import("../src/components/ForestPlot");
    const d = axisDomain([{ name: "a", lift: -0.02, low: -0.07, high: 0.03, tone: "neutral" }]);
    expect(d.min).toBeLessThanOrEqual(-0.07);
    expect(d.max).toBeGreaterThanOrEqual(0.03);
    expect(d.ticks).toContain(0);
    expect(d.ticks.length).toBeGreaterThanOrEqual(3);
  });
});

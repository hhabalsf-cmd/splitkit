import { describe, expect, it, vi } from "vitest";
import { SplitkitClient } from "../src/client.js";
import type { ExperimentConfig } from "../src/types.js";

const RUNNING: ExperimentConfig = {
  key: "checkout-v2",
  salt: "checkout-v2",
  status: "running",
  variants: [
    { name: "control", weight: 0.5 },
    { name: "treatment", weight: 0.5 },
  ],
};

function ok(data: unknown) {
  return new Response(JSON.stringify({ success: true, data, error: null }), { status: 200 });
}

function mockFetch(config: ExperimentConfig = RUNNING) {
  const calls: { url: string; body: any }[] = [];
  const fn = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = String(url);
    calls.push({ url: u, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (u.endsWith("/config")) return ok(config);
    if (u.endsWith("/v1/exposures")) return ok({ accepted: 1, duplicates: 0, rejected: 0 });
    if (u.endsWith("/v1/events")) return ok({ accepted: 1, duplicates: 0 });
    return new Response("{}", { status: 404 });
  });
  return { fn: fn as unknown as typeof fetch, calls };
}

let counter = 0;
const makeClient = (fetchFn: typeof fetch, extra = {}) =>
  new SplitkitClient({
    baseUrl: "https://api.test/",
    fetchFn,
    idFn: () => `id-${++counter}`,
    now: () => new Date("2026-01-01T00:00:00Z"),
    ...extra,
  });

describe("getVariant", () => {
  it("assigns locally and logs exactly one exposure per user", async () => {
    const { fn, calls } = mockFetch();
    const client = makeClient(fn);
    const first = await client.getVariant("checkout-v2", "user-1");
    const again = await client.getVariant("checkout-v2", "user-1");
    expect(first).toBe(again);
    expect(["control", "treatment"]).toContain(first);
    await client.flush();
    const exposurePosts = calls.filter((c) => c.url.endsWith("/v1/exposures"));
    expect(exposurePosts).toHaveLength(1);
    expect(exposurePosts[0]!.body.exposures).toEqual([
      { experiment_key: "checkout-v2", user_id: "user-1", variant: first },
    ]);
  });

  it("fetches config once even under concurrent calls", async () => {
    const { fn, calls } = mockFetch();
    const client = makeClient(fn);
    await Promise.all([client.getVariant("checkout-v2", "a"), client.getVariant("checkout-v2", "b")]);
    expect(calls.filter((c) => c.url.endsWith("/config"))).toHaveLength(1);
  });

  it("returns null and logs nothing when the experiment is not running", async () => {
    const { fn, calls } = mockFetch({ ...RUNNING, status: "stopped" });
    const client = makeClient(fn);
    expect(await client.getVariant("checkout-v2", "user-1")).toBeNull();
    await client.flush();
    expect(calls.some((c) => c.url.endsWith("/v1/exposures"))).toBe(false);
  });

  it("returns null instead of throwing when the API is down", async () => {
    const fn = vi.fn(async () => {
      throw new TypeError("network down");
    }) as unknown as typeof fetch;
    const client = makeClient(fn);
    expect(await client.getVariant("checkout-v2", "user-1")).toBeNull();
  });

  it("rejects malformed experiment keys", async () => {
    const { fn } = mockFetch();
    await expect(makeClient(fn).getVariant("../admin", "u")).rejects.toThrow(/experiment key/);
  });

  it("encodes the experiment key into the config URL", async () => {
    const { fn, calls } = mockFetch();
    await makeClient(fn).getVariant("checkout-v2", "u");
    expect(calls[0]!.url).toBe("https://api.test/v1/experiments/checkout-v2/config");
  });
});

describe("track + flush", () => {
  it("batches events with client-generated ids for idempotent retries", async () => {
    const { fn, calls } = mockFetch();
    const client = makeClient(fn, { maxBatchSize: 2 });
    client.track("u1", "purchase", 19.99);
    client.track("u1", "page_view");
    client.track("u2", "purchase", 5);
    const result = await client.flush();
    const posts = calls.filter((c) => c.url.endsWith("/v1/events"));
    expect(posts).toHaveLength(2); // 2 + 1
    expect(posts[0]!.body.events[0]).toMatchObject({
      user_id: "u1",
      event_name: "purchase",
      value: 19.99,
      ts: "2026-01-01T00:00:00.000Z",
    });
    expect(posts[0]!.body.events[0].event_id).toMatch(/^id-/);
    expect(result.sent).toBe(3);
    expect(client.pending()).toBe(0);
  });

  it("re-queues on network or 5xx failure and resends the same event ids", async () => {
    let fail = true;
    const bodies: any[] = [];
    const fn = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init!.body)));
      if (fail) return new Response("oops", { status: 503 });
      return ok({ accepted: 1, duplicates: 0 });
    }) as unknown as typeof fetch;
    const client = makeClient(fn);
    client.track("u1", "purchase", 1);
    const first = await client.flush();
    expect(first.failed).toBe(1);
    expect(client.pending()).toBe(1);
    fail = false;
    await client.flush();
    expect(client.pending()).toBe(0);
    expect(bodies[1].events[0].event_id).toBe(bodies[0].events[0].event_id);
  });

  it("drops a batch the server rejects as invalid (4xx) instead of retrying forever", async () => {
    const fn = vi.fn(async () => new Response("bad", { status: 422 })) as unknown as typeof fetch;
    const client = makeClient(fn);
    client.track("u1", "purchase", 1);
    const result = await client.flush();
    expect(result.dropped).toBe(1);
    expect(client.pending()).toBe(0);
  });

  it("bounds the queue by dropping the oldest items", () => {
    const { fn } = mockFetch();
    const client = makeClient(fn, { maxQueueSize: 2 });
    client.track("u", "a");
    client.track("u", "b");
    client.track("u", "c");
    expect(client.pending()).toBe(2);
  });

  it("validates event names and values up front", () => {
    const { fn } = mockFetch();
    const client = makeClient(fn);
    expect(() => client.track("u", "Bad Name!")).toThrow(/event name/);
    expect(() => client.track("u", "ok", Number.NaN)).toThrow(/value/);
    expect(() => client.track("", "ok")).toThrow(/user/);
  });

  it("flushes automatically on an interval and stops on close", async () => {
    vi.useFakeTimers();
    const { fn, calls } = mockFetch();
    const client = makeClient(fn, { flushIntervalMs: 1000 });
    client.track("u", "purchase", 1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls.filter((c) => c.url.endsWith("/v1/events"))).toHaveLength(1);
    client.close();
    client.track("u", "purchase", 2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(calls.filter((c) => c.url.endsWith("/v1/events"))).toHaveLength(1);
    vi.useRealTimers();
  });
});

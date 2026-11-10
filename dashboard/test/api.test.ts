import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError, loadStoredKey, storeKey } from "../src/api";

function respond(status: number, body: unknown) {
  return vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
}

describe("ApiClient", () => {
  it("sends the admin key and unwraps the envelope", async () => {
    const fetchFn = respond(200, { success: true, data: [{ key: "a" }], error: null });
    const api = new ApiClient("secret-key-123456", fetchFn);
    await expect(api.listExperiments()).resolves.toEqual([{ key: "a" }]);
    const [url, init] = (fetchFn as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/v1/experiments");
    expect((init as RequestInit).headers).toMatchObject({ "X-API-Key": "secret-key-123456" });
  });

  it("surfaces the server's error message with status", async () => {
    const api = new ApiClient("k".repeat(16), respond(409, { success: false, data: null, error: "not enough data" }));
    const err = await api.results("x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(409);
    expect((err as ApiError).message).toBe("not enough data");
  });

  it("encodes keys and query parameters", async () => {
    const fetchFn = respond(200, { success: true, data: { metric: "m", type: "mean", points: [] }, error: null });
    await new ApiClient("k".repeat(16), fetchFn).timeline("a b", "rev", 8);
    const [url] = (fetchFn as unknown as ReturnType<typeof vi.fn>).mock.calls[0]!;
    expect(url).toBe("/v1/experiments/a%20b/timeline?metric=rev&points=8");
  });

  it("reports network failures as status 0", async () => {
    const fetchFn = vi.fn(async () => {
      throw new TypeError("offline");
    }) as unknown as typeof fetch;
    const err = await new ApiClient("k".repeat(16), fetchFn).listExperiments().catch((e: unknown) => e);
    expect((err as ApiError).status).toBe(0);
  });
});

describe("key storage", () => {
  it("round-trips through sessionStorage only", () => {
    expect(loadStoredKey()).toBeNull();
    storeKey("abc");
    expect(loadStoredKey()).toBe("abc");
    expect(localStorage.getItem("splitkit.adminKey")).toBeNull();
    storeKey(null);
    expect(loadStoredKey()).toBeNull();
  });
});

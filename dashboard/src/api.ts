import type { Envelope, Experiment, Readout, Timeline } from "./types";

const STORAGE_KEY = "splitkit.adminKey";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The key lives in sessionStorage: gone when the tab closes, never in localStorage. */
export function loadStoredKey(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function storeKey(key: string | null): void {
  try {
    if (key) sessionStorage.setItem(STORAGE_KEY, key);
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage blocked (private mode): the key just won't persist across reloads
  }
}

export class ApiClient {
  constructor(
    private readonly adminKey: string,
    private readonly fetchFn: typeof fetch = globalThis.fetch.bind(globalThis),
  ) {}

  listExperiments(): Promise<Experiment[]> {
    return this.get("/v1/experiments");
  }

  results(key: string): Promise<Readout> {
    return this.get(`/v1/experiments/${encodeURIComponent(key)}/results`);
  }

  timeline(key: string, metric: string, points = 12): Promise<Timeline> {
    const q = new URLSearchParams({ metric, points: String(points) });
    return this.get(`/v1/experiments/${encodeURIComponent(key)}/timeline?${q}`);
  }

  private async get<T>(path: string): Promise<T> {
    let res: Response;
    try {
      res = await this.fetchFn(path, { headers: { "X-API-Key": this.adminKey } });
    } catch {
      throw new ApiError(0, "Can't reach the Splitkit API. Is the server running?");
    }
    let body: Envelope<T> | null = null;
    try {
      body = (await res.json()) as Envelope<T>;
    } catch {
      // non-JSON body (proxy error page etc.) falls through to the generic message
    }
    if (!res.ok || !body?.success || body.data === null) {
      throw new ApiError(res.status, body?.error ?? `Request failed (${res.status})`);
    }
    return body.data;
  }
}

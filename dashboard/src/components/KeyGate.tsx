import { type FormEvent, useState } from "react";
import { ApiClient, ApiError } from "../api";

const MIN_KEY = 16;

interface Props {
  readonly onUnlock: (key: string) => void;
  readonly notice?: string | null;
}

export function KeyGate({ onUnlock, notice }: Props) {
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = key.trim();
    if (trimmed.length < MIN_KEY) {
      setError(`Admin keys are at least ${MIN_KEY} characters.`);
      return;
    }
    setChecking(true);
    setError(null);
    try {
      await new ApiClient(trimmed).listExperiments(); // proves the key before we keep it
      onUnlock(trimmed);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "That key was rejected." : (err as Error).message);
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className="gate">
      <form onSubmit={submit} className="gate-card reveal">
        <p className="eyebrow">Splitkit</p>
        <h1>Readouts</h1>
        <p className="muted">Enter the admin API key for this deployment. It's kept for this tab only.</p>
        {notice && <p className="gate-notice">{notice}</p>}
        <label htmlFor="admin-key">Admin key</label>
        <input
          id="admin-key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={key}
          onChange={(e) => setKey(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "key-error" : undefined}
        />
        {error && (
          <p id="key-error" className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={checking}>
          {checking ? "Checking…" : "Open readouts"}
        </button>
      </form>
    </main>
  );
}

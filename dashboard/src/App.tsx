import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, loadStoredKey, storeKey } from "./api";
import { ExperimentList } from "./components/ExperimentList";
import { KeyGate } from "./components/KeyGate";
import { Readout } from "./components/Readout";

/** Hash routes need no server-side fallback: #/ (index) and #/exp/<key>. */
function parseRoute(hash: string): { readonly view: "list" } | { readonly view: "exp"; readonly key: string } {
  const match = /^#\/exp\/(.+)$/.exec(hash);
  if (!match?.[1]) return { view: "list" };
  try {
    return { view: "exp", key: decodeURIComponent(match[1]) };
  } catch {
    return { view: "list" };
  }
}

export function App() {
  const [adminKey, setAdminKey] = useState<string | null>(loadStoredKey);
  const [notice, setNotice] = useState<string | null>(null);
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));

  useEffect(() => {
    const onHash = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const api = useMemo(() => (adminKey ? new ApiClient(adminKey) : null), [adminKey]);

  const signOut = useCallback((message: string | null = null) => {
    storeKey(null);
    setAdminKey(null);
    setNotice(message);
  }, []);
  const onUnauthorized = useCallback(() => signOut("Your key is no longer accepted. Enter it again."), [signOut]);

  if (!api) {
    return (
      <KeyGate
        notice={notice}
        onUnlock={(key) => {
          storeKey(key);
          setNotice(null);
          setAdminKey(key);
        }}
      />
    );
  }

  return (
    <div className="shell">
      <nav className="topbar">
        <a href="#/" className="brand">
          <span className="brand-mark" aria-hidden="true" />
          Splitkit
        </a>
        <button type="button" className="link" onClick={() => signOut()}>
          Sign out
        </button>
      </nav>
      <main className="page">
        {route.view === "exp" ? (
          <>
            <a href="#/" className="back">
              ← All experiments
            </a>
            <Readout api={api} experimentKey={route.key} onUnauthorized={onUnauthorized} />
          </>
        ) : (
          <ExperimentList api={api} onUnauthorized={onUnauthorized} />
        )}
      </main>
    </div>
  );
}

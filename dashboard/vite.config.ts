/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served by FastAPI at /dashboard/ in production (same origin as the API).
// In dev, Vite proxies API calls to a local uvicorn on :8000.
export default defineConfig({
  base: "/dashboard/",
  plugins: [react()],
  server: { proxy: { "/v1": "http://127.0.0.1:8000", "/health": "http://127.0.0.1:8000" } },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", globals: true, setupFiles: ["./test/setup.ts"] },
});

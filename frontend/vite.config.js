import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, vite serves the UI on :5173 and proxies API calls to the
// FastAPI backend on :8000. In production there is no proxy at all:
// FastAPI serves the built files itself (same origin, no CORS needed).
const BACKEND = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      ["/map", "/villagers", "/tick", "/time", "/history"].map((p) => [
        p,
        { target: BACKEND, changeOrigin: true },
      ])
    ),
  },
});

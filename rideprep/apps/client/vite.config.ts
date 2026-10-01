import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The course-builder API runs on :8000 (docker compose or `uvicorn api.app:app`); the client calls it via /api.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.RIDEPREP_API ?? "http://localhost:8000", changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  worker: { format: "es" },
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
});

import react from "@vitejs/plugin-react";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { defineConfig, Plugin } from "vite";

/** Serve/emit three.js' Draco decoder at /draco/ (Google 3D tiles are Draco-compressed). */
function dracoDecoder(): Plugin {
  const dir = join(dirname(fileURLToPath(import.meta.url)), "node_modules/three/examples/jsm/libs/draco/gltf");
  return {
    name: "rideprep-draco",
    configureServer(server) {
      server.middlewares.use("/draco", (req, res, next) => {
        const f = (req.url ?? "").replace(/^\//, "").split("?")[0];
        if (!readdirSync(dir).includes(f)) return next();
        res.setHeader("Content-Type", f.endsWith(".wasm") ? "application/wasm" : "text/javascript");
        res.end(readFileSync(join(dir, f)));
      });
    },
    generateBundle() {
      for (const f of readdirSync(dir)) this.emitFile({ type: "asset", fileName: `draco/${f}`, source: readFileSync(join(dir, f)) });
    },
  };
}

// The course-builder API runs on :8000 (docker compose or `uvicorn api.app:app`); the client calls it via /api.
export default defineConfig({
  plugins: [react(), dracoDecoder()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.RIDEPREP_API ?? "http://localhost:8000", changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  worker: { format: "es" },
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served by FastAPI as a static bundle in production (D1).
// In dev, /api and /ws proxy to the local engine (default port 8471;
// override with NEURAI_API_PORT to run several engine instances side by side).
const apiPort = process.env.NEURAI_API_PORT || "8471";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: `http://127.0.0.1:${apiPort}`, changeOrigin: true },
      "/ws": { target: `ws://127.0.0.1:${apiPort}`, ws: true },
    },
  },
  build: { outDir: "dist" },
});

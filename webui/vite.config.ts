import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served by FastAPI as a static bundle in production (D1).
// In dev, /api and /ws proxy to the local engine when it exists.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8471", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8471", ws: true },
    },
  },
  build: { outDir: "dist" },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build lands inside the Python package (the Pulse pattern): installing
// okto-nexus serves the dashboard without Node on the user's machine.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/okto_nexus/adapters/inbound/http/static",
    emptyOutDir: true,
  },
  server: {
    port: 5202,
    proxy: {
      "/api": "http://127.0.0.1:8202",
      "/mcp": "http://127.0.0.1:8202",
    },
  },
});

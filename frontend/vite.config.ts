import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.ASM_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    // Same-Origin aus Sicht des Browsers: Cookies und CSRF funktionieren ohne CORS.
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    // Kein Inline-Code → kompatibel mit der strikten Content-Security-Policy des Backends.
    assetsInlineLimit: 0,
  },
});

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // In Docker Compose the API service hostname is "api"; on the host use localhost.
  const proxyTarget = env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      proxy: {
        // Same-origin API → no CORS when UI is opened via LAN IP
        "/api": {
          target: proxyTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
        "/ws": {
          target: proxyTarget.replace(/^http/, "ws"),
          ws: true,
          changeOrigin: true,
        },
      },
    },
    optimizeDeps: {
      include: ["maplibre-gl"],
    },
  };
});

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.PANELTWIN_API_TARGET || "http://127.0.0.1:8000";

  return {
    base: env.VITE_BASE_PATH || "/",
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/backend": {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/backend/, ""),
        },
        "/health": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});

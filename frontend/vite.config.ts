import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { visualizer } from "rollup-plugin-visualizer";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  plugins: [
    react(),
    // Generates dist/stats.html — open after `npm run build` to audit bundle
    visualizer({ filename: "dist/stats.html", open: false, gzipSize: true, brotliSize: true }),
  ],
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: {
          // Core React runtime — cached aggressively by browsers
          "vendor-react": ["react", "react-dom"],
          // Heavy chart libraries — separated so dashboard bundle stays small
          "vendor-recharts": ["recharts"],
          "vendor-lightweight": ["lightweight-charts"],
          // Data-fetching infrastructure
          "vendor-query": ["@tanstack/react-query", "axios"],
          // Zustand state
          "vendor-zustand": ["zustand"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://backend:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: process.env.VITE_WS_TARGET ?? "ws://backend:8000",
        ws: true,
      },
    },
  },
});

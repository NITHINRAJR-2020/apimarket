import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
  proxy: {
    "/api": {
      target: "https://apimarket-mp7s.onrender.com",
      changeOrigin: true,
    },
    "/market": {
      target: "https://apimarket-mp7s.onrender.com",
      changeOrigin: true,
    },
    "/health": {
      target: "https://apimarket-mp7s.onrender.com",
      changeOrigin: true,
    },
  },
  },
});

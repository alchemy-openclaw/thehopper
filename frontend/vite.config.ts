import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Must match the static mount in backend/main.py — assets are requested at
  // this prefix, so the two move together or every asset 404s.
  base: '/karaokespot/',
  server: {
    port: 5173,
    // Proxy /api to the FastAPI backend during local dev
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});

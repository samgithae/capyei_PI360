import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: process.env.VITE_BASE_URL || '/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // Same-origin API in development so the session cookie and CSRF work.
    proxy: {
      '/api': process.env.VITE_API_PROXY || 'http://localhost:8000',
      '/admin': process.env.VITE_API_PROXY || 'http://localhost:8000',
    },
  },
  build: {
    chunkSizeWarningLimit: 3000,
  },
});

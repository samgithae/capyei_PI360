import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

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
      '^/admin/': process.env.VITE_API_PROXY || 'http://localhost:8000',
    },
  },
  test: { environment: 'jsdom', setupFiles: ['./src/test-setup.ts'] },
  build: {
    chunkSizeWarningLimit: 3000,
  },
});

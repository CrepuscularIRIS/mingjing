import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // `@/…` → `src/…`, matching tsconfig paths. Vitest reads this config too,
      // so the alias resolves in tests as well as the dev server / build.
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // Proxy API calls to the FastAPI backend (port 8000) to avoid CORS in dev.
    proxy: {
      '/runs': 'http://localhost:8000',
      '/sources': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/schemas': 'http://localhost:8000',
    },
  },
})

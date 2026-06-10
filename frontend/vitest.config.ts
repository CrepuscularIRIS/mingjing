import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Separate vitest config to avoid vite v8/vitest vite version conflicts.
export default defineConfig({
  plugins: [react()],
  resolve: {
    // Mirror vite.config.ts so `@/…` → `src/…` resolves under Vitest too.
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})

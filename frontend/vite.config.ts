import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Dev: `npm run dev` (porta 5173) faz proxy de /api para o servidor Python (python -m emporio.web, porta 8000).
// Prod: `npm run build` gera frontend/dist, que o próprio servidor Python serve em http://127.0.0.1:8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})

import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// FastAPI (uv run python -m chessllm) serves the API, the pieces and the sounds.
const backend = 'http://127.0.0.1:8000'

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  // The build goes into FastAPI's static files: it serves index.html at /next and the rest under /static/dist/.
  // The dev server serves the app at / instead.
  base: command === 'build' ? '/static/dist/' : '/',
  build: {
    outDir: path.resolve(import.meta.dirname, '../chessllm/static/dist'),
    emptyOutDir: true,
  },
  server: {
    proxy: { '/api': backend, '/static': backend },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
}))

import { readFileSync } from 'node:fs'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import type { Plugin } from 'vite'
import { defineConfig } from 'vitest/config'

// FastAPI (uv run python -m chessllm) serves the API, the pieces and the sounds. CHESSLLM_BACKEND points at another one.
const backend = process.env.CHESSLLM_BACKEND ?? 'http://127.0.0.1:8000'

// Writes the fingerprint of the API description src/api/schema.ts was generated from (its first line) into the
// build as api-fingerprint.txt. FastAPI refuses to serve a build whose fingerprint isn't that of its own API.
function apiFingerprint(): Plugin {
  return {
    name: 'chessllm-api-fingerprint',
    apply: 'build',
    generateBundle() {
      const schema = path.resolve(import.meta.dirname, 'src/api/schema.ts')
      const header = readFileSync(schema, 'utf-8').split('\n', 1)[0]
      const fingerprint = /sha256 ([0-9a-f]{64})$/.exec(header)?.[1]
      if (fingerprint === undefined) {
        this.error(`${schema} doesn't start with the API fingerprint: run \`uv run python -m scripts.generate_api_types\``)
      }
      this.emitFile({ type: 'asset', fileName: 'api-fingerprint.txt', source: `${fingerprint}\n` })
    },
  }
}

export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss(), apiFingerprint()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
  // The build goes into FastAPI's static files: it serves index.html at / and the rest under /static/dist/.
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

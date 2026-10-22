// The Playwright journeys (`pnpm e2e`): the built app at / against FastAPI with scripted LLM players
// (tests/e2e/server.py), so they run without Ollama. Build first: `pnpm build`.
import { createServer } from 'node:net'
import { defineConfig, devices } from '@playwright/test'

// A free port, picked once: the workers load this file again, and inherit it through the environment.
async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address() as { port: number }
      server.close(() => resolve(port))
    })
  })
}
process.env.E2E_PORT ??= String(await freePort())
const baseURL = `http://127.0.0.1:${process.env.E2E_PORT}`

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.e2e.ts',
  // The backend plays one game at a time, so the journeys run one after another.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  reporter: 'list',
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `uv run python -m tests.e2e.server --port ${process.env.E2E_PORT}`,
    cwd: '..',
    url: `${baseURL}/api/models`,
    reuseExistingServer: false,
    stdout: 'pipe',
  },
})

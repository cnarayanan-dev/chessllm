import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from '@/App'

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

function stubModels(response: Response) {
  const fetch = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetch)
  return fetch
}

test('lists the models the API offers', async () => {
  const fetch = stubModels(
    Response.json([
      { name: 'qwen3.5:9b', thinking: true, sampling: { temperature: 0.6 } },
      { name: 'gemma3:4b', thinking: false, sampling: null },
    ]),
  )

  renderApp()

  expect(await screen.findByText('qwen3.5:9b')).toBeInTheDocument()
  expect(screen.getByText('gemma3:4b')).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledWith('/api/models')
  expect(screen.getByRole('button', { name: 'Reload models' })).toBeInTheDocument()
})

test('says so when the models cannot be loaded', async () => {
  stubModels(new Response('boom', { status: 500 }))

  renderApp()

  expect(await screen.findByText(/Couldn't load the models/)).toBeInTheDocument()
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from '@/App'
import { theBoard } from '@/test/fakeChessboard'

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

test('shows the board in a fixed position, to compare with the old page', async () => {
  stubModels(Response.json([]))

  renderApp()

  const board = theBoard()
  await waitFor(() => expect(board.marked('check')).toEqual(['h8']))
  expect(board.position).toBe('r6K/1P6/8/8/8/8/5k2/8')
  expect(board.marked('last-move')).toEqual(['a1', 'a8'])
  expect(board.input?.color).toBe('w')
})

test('says so when the models cannot be loaded', async () => {
  stubModels(new Response('boom', { status: 500 }))

  renderApp()

  expect(await screen.findByText(/Couldn't load the models/)).toBeInTheDocument()
})

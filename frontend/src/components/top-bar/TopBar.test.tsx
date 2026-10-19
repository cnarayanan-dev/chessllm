import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { TopBar } from '@/components/top-bar/TopBar'

const topBar = () => screen.getByRole('banner')
/** The top bar's links and buttons, in order, by their accessible names. */
const actions = () =>
  [...topBar().querySelectorAll('a, button')].map((element) => element.getAttribute('aria-label') ?? element.textContent)

describe('on the game page', () => {
  test('shows the rook mark and "ChessLLM", then Analytics, New game and Settings', () => {
    render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)

    expect(actions()).toEqual(['ChessLLM', 'Analytics', 'New game', 'Settings'])
    expect(screen.getByRole('link', { name: 'ChessLLM' }).querySelector('img')).toHaveAttribute(
      'src',
      expect.stringContaining('rook'),
    )
    expect(screen.getByRole('link', { name: 'ChessLLM' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Analytics' })).toHaveAttribute('href', '/analytics')
  })

  test('New game and Settings are buttons that call the page', async () => {
    const onNewGame = vi.fn()
    const onSettings = vi.fn()
    render(<TopBar onNewGame={onNewGame} onSettings={onSettings} />)

    await userEvent.click(screen.getByRole('button', { name: 'New game' }))
    await userEvent.click(screen.getByRole('button', { name: 'Settings' }))

    expect(onNewGame).toHaveBeenCalledOnce()
    expect(onSettings).toHaveBeenCalledOnce()
  })

  test('the Settings button has no shortcut on it; its tooltip reads "Settings ⌘K"', async () => {
    render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)
    const settings = screen.getByRole('button', { name: 'Settings' })

    expect(settings).toHaveTextContent(/^Settings$/)
    expect(within(topBar()).queryByText('⌘K')).not.toBeInTheDocument()

    await userEvent.hover(settings)

    const tooltip = await screen.findByText('⌘K')
    expect(tooltip.closest('[data-slot=tooltip-content]')).toHaveTextContent('Settings ⌘K')
  })
})

describe('on a page without the game', () => {
  test('New game and Settings are links that do it on the game page', () => {
    render(<TopBar />)

    expect(actions()).toEqual(['ChessLLM', 'Analytics', 'New game', 'Settings'])
    expect(screen.getByRole('link', { name: 'New game' })).toHaveAttribute('href', '/?then=new-game')
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/?then=settings')
  })

  test('the current page is marked', () => {
    render(<TopBar current="analytics" />)

    expect(screen.getByRole('link', { name: 'Analytics' })).toHaveAttribute('aria-current', 'page')
  })
})

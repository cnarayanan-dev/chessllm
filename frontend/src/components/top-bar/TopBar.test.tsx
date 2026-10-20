import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { TopBar } from '@/components/top-bar/TopBar'

const topBar = () => screen.getByRole('banner')
/** The open Tooltip, once it shows. */
const tooltip = () =>
  waitFor(() => {
    const content = document.querySelector('[data-slot=tooltip-content]')
    expect(content).toBeInTheDocument()
    return content
  })
/** The top bar's links and buttons, in order, by their accessible names. */
const actions = () =>
  [...topBar().querySelectorAll('a, button')].map((element) => element.getAttribute('aria-label') ?? element.textContent)

describe('on the game page', () => {
  test('shows the rook mark and "ChessLLM", then Analytics, New game and Settings, and ends with Preferences', () => {
    render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)

    expect(actions()).toEqual(['ChessLLM', 'Analytics', 'New game', 'Settings', 'Preferences'])
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

describe('Preferences', () => {
  afterEach(() => localStorage.clear())

  test('is a gear icon button whose tooltip reads "Preferences"', async () => {
    render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)
    const preferences = screen.getByRole('button', { name: 'Preferences' })

    expect(preferences).toHaveTextContent(/^$/)
    expect(preferences.querySelector('svg')).toHaveClass('lucide-settings')

    await userEvent.hover(preferences)

    expect(await tooltip()).toHaveTextContent(/^Preferences$/)
  })

  test('opens a panel with the Move sound switch, off in a browser that never turned it on', async () => {
    render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)

    await userEvent.click(screen.getByRole('button', { name: 'Preferences' }))

    const panel = await screen.findByRole('dialog', { name: 'Preferences' })
    expect(within(panel).getByRole('switch', { name: 'Move sound' })).not.toBeChecked()
  })

  test('Move sound applies at once and is remembered in this browser', async () => {
    const { unmount } = render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Preferences' }))

    await userEvent.click(await screen.findByRole('switch', { name: 'Move sound' }))

    expect(screen.getByRole('switch', { name: 'Move sound' })).toBeChecked()
    expect(localStorage.getItem('chessllm.moveSound')).toBe('on')

    unmount()
    render(<TopBar />)
    await userEvent.click(screen.getByRole('button', { name: 'Preferences' }))
    expect(await screen.findByRole('switch', { name: 'Move sound' })).toBeChecked()
  })

  const explanation = 'A click on every move. Applies at once, in this browser.'

  test("Move sound's explanation is a tooltip on hover, not a text line, and its aria-description", async () => {
    render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Preferences' }))
    const panel = await screen.findByRole('dialog', { name: 'Preferences' })

    expect(panel).not.toHaveTextContent(explanation)
    expect(within(panel).getByRole('switch', { name: 'Move sound' })).toHaveAttribute('aria-description', explanation)

    await userEvent.hover(within(panel).getByText('Move sound'))

    expect(await tooltip()).toHaveTextContent(explanation)
  })

  test("with the keyboard alone, Move sound's explanation shows once its switch has focus", async () => {
    render(<TopBar onNewGame={() => {}} onSettings={() => {}} />)
    for (const _ of ['ChessLLM', 'Analytics', 'New game', 'Settings', 'Preferences']) await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Preferences' })).toHaveFocus()

    await userEvent.keyboard('{Enter}')

    const sound = await screen.findByRole('switch', { name: 'Move sound' })
    await waitFor(() => expect(sound).toHaveFocus())
    expect(await tooltip()).toHaveTextContent(explanation)
  })
})

describe('on a page without the game', () => {
  test('New game and Settings are links that do it on the game page; Preferences is there too', () => {
    render(<TopBar />)

    expect(actions()).toEqual(['ChessLLM', 'Analytics', 'New game', 'Settings', 'Preferences'])
    expect(screen.getByRole('link', { name: 'New game' })).toHaveAttribute('href', '/?then=new-game')
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/?then=settings')
  })

  test('the current page is marked', () => {
    render(<TopBar current="analytics" />)

    expect(screen.getByRole('link', { name: 'Analytics' })).toHaveAttribute('aria-current', 'page')
  })
})

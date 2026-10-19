import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import { resetBoards } from '@/test/fakeChessboard'

// jsdom can't draw cm-chessboard's SVG, so every test gets the fake board.
vi.mock('cm-chessboard/src/Chessboard.js', () => import('@/test/fakeChessboard'))
vi.mock('cm-chessboard/src/extensions/markers/Markers.js', () => import('@/test/fakeChessboard'))
vi.mock('cm-chessboard/src/extensions/promotion-dialog/PromotionDialog.js', () => import('@/test/fakeChessboard'))

afterEach(() => {
  cleanup()
  resetBoards()
  vi.unstubAllGlobals()
})

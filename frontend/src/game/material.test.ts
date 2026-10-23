import { expect, test } from 'vitest'
import type { Color, Ply } from '@/api/types'
import { material } from '@/game/material'

type Resolution = NonNullable<Ply['resolution']>

/** A ply by `color` from one position to the next: only the pieces in its FENs count. */
const ply = (color: Color, before: string, after: string, resolution?: Resolution): Ply => ({
  ply: 1,
  color,
  move: '',
  written: '',
  fen_before: `${before} ${color[0]} - - 0 1`,
  fen_after: `${after} ${color === 'white' ? 'b' : 'w'} - - 0 1`,
  check: false,
  time_s: 0,
  ...(resolution ? { resolution } : {}),
})
const NONE = { p: 0, n: 0, b: 0, r: 0, q: 0, k: 0 }

test("a capture is the opponent's piece that disappeared on the side's ply; +N is the material it is ahead", () => {
  const plies = [
    ply('white', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR', 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR'),
    ply('black', 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR', 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR'),
    ply('white', 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR', 'rnbqkbnr/ppp1pppp/8/3P4/8/8/PPPP1PPP/RNBQKBNR'),
  ]
  const fen = plies[2].fen_after

  expect(material(plies, fen, 'white')).toEqual({ taken: { ...NONE, p: 1 }, spawned: NONE, ahead: 1 })
  expect(material(plies, fen, 'black')).toEqual({ taken: NONE, spawned: NONE, ahead: -1 })
})

const spawn = (to: string, piece: string): Resolution => ({
  kind: 'spawn',
  from: null,
  to,
  piece,
  rook: null,
  reason: `no such piece on the board; one appears on ${to}`,
})

test('under Chaos rules a queen spawned after the queen was captured hides neither: one is taken, one spawned', () => {
  const plies = [
    ply('white', '3qk3/8/8/8/8/8/8/3QK3', '3Qk3/8/8/8/8/8/8/4K3'),
    ply('black', '3Qk3/8/8/8/8/8/8/4K3', '3Qk3/8/8/8/7q/8/8/4K3', spawn('h4', 'q')),
  ]
  const fen = plies[1].fen_after

  expect(material(plies, fen, 'white')).toEqual({ taken: { ...NONE, q: 1 }, spawned: NONE, ahead: 0 })
  expect(material(plies, fen, 'black')).toEqual({ taken: NONE, spawned: { ...NONE, q: 1 }, ahead: 0 })
})

test('en passant takes the pawn that disappeared from beside the capturing pawn', () => {
  const plies = [ply('white', 'rnbqkbnr/1pp1pppp/p7/3pP3/8/8/PPPP1PPP/RNBQKBNR', 'rnbqkbnr/1pp1pppp/p2P4/8/8/8/PPPP1PPP/RNBQKBNR')]

  expect(material(plies, plies[0].fen_after, 'white')).toEqual({ taken: { ...NONE, p: 1 }, spawned: NONE, ahead: 1 })
})

test('a promotion is neither a capture nor a spawn: the pawn becomes the piece, and +N grows by the difference', () => {
  const plies = [ply('white', '4k3/P7/8/8/8/8/8/4K3', 'Q3k3/8/8/8/8/8/8/4K3')]

  expect(material(plies, plies[0].fen_after, 'white')).toEqual({ taken: NONE, spawned: NONE, ahead: 9 })
  expect(material(plies, plies[0].fen_after, 'black')).toEqual({ taken: NONE, spawned: NONE, ahead: -9 })
})

test('a capture-promotion takes the piece it lands on, and an underpromotion spawns nothing either', () => {
  const plies = [
    ply('white', '1r2k3/P7/8/8/8/8/p7/4K3', '1N2k3/8/8/8/8/8/p7/4K3'),
    ply('black', '1N2k3/8/8/8/8/8/p7/4K3', '1N2k3/8/8/8/8/8/8/r3K3'),
  ]
  const fen = plies[1].fen_after

  expect(material(plies, fen, 'white')).toEqual({ taken: { ...NONE, r: 1 }, spawned: NONE, ahead: -2 })
  expect(material(plies, fen, 'black')).toEqual({ taken: NONE, spawned: NONE, ahead: 2 })
})

test('castling moves two pieces and takes none', () => {
  const plies = [ply('white', 'r3k2r/8/8/8/8/8/8/R3K2R', 'r3k2r/8/8/8/8/8/8/R4RK1')]

  expect(material(plies, plies[0].fen_after, 'white')).toEqual({ taken: NONE, spawned: NONE, ahead: 0 })
})

test('a spawn onto a pawn of its own side is still a spawn, not a promotion', () => {
  const plies = [ply('black', '4k3/8/8/8/4p3/8/8/4K3', '4k3/8/8/8/4q3/8/8/4K3', spawn('e4', 'q'))]

  expect(material(plies, plies[0].fen_after, 'black')).toEqual({ taken: NONE, spawned: { ...NONE, q: 1 }, ahead: 9 })
})

test('a spawn that lands on a piece of the other side takes it as well', () => {
  const plies = [ply('black', '4k3/8/8/8/4N3/8/8/4K3', '4k3/8/8/8/4q3/8/8/4K3', spawn('e4', 'q'))]

  expect(material(plies, plies[0].fen_after, 'black')).toEqual({
    taken: { ...NONE, n: 1 },
    spawned: { ...NONE, q: 1 },
    ahead: 9,
  })
})

test('under Chaos rules a King capture shows the king taken', () => {
  const plies = [ply('white', '4k3/8/8/8/8/8/8/4R1K1', '4R3/8/8/8/8/8/8/6K1')]

  expect(material(plies, plies[0].fen_after, 'white')).toEqual({ taken: { ...NONE, k: 1 }, spawned: NONE, ahead: 5 })
})

test('at the start position, before any ply, nothing is taken or spawned', () => {
  const start = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

  expect(material([], start, 'white')).toEqual({ taken: NONE, spawned: NONE, ahead: 0 })
})

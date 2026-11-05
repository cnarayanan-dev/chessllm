// PROTOTYPE, throwaway: the floating bar that switches a prototype's variants through ?variant=. Dev builds only.
import { useEffect, useState } from 'react'

/** The variant in the address, or the first one. Re-renders when the bar changes it. */
export function useVariant(keys: readonly string[], param = 'variant'): string {
  const read = () => {
    const asked = new URLSearchParams(window.location.search).get(param) ?? ''
    return keys.includes(asked) ? asked : keys[0]
  }
  const [variant, setVariant] = useState(read)
  useEffect(() => {
    const onChange = () => setVariant(read())
    window.addEventListener('prototype-variant', onChange)
    window.addEventListener('popstate', onChange)
    return () => {
      window.removeEventListener('prototype-variant', onChange)
      window.removeEventListener('popstate', onChange)
    }
  })
  return variant
}

function go(key: string, param: string) {
  const url = new URL(window.location.href)
  url.searchParams.set(param, key)
  window.history.replaceState(null, '', url)
  window.dispatchEvent(new Event('prototype-variant'))
}

type PrototypeSwitcherProps = {
  variants: readonly { key: string; name: string }[]
  current: string
  /** A second prototype on the same page: its own address param, cycle keys and a bar stacked above. */
  param?: string
  keys?: readonly [string, string]
  stack?: number
}

/** ← and → already step the move history on the game page, so [ and ] cycle the variants. */
export function PrototypeSwitcher({ variants, current, param = 'variant', keys = ['[', ']'], stack = 0 }: PrototypeSwitcherProps) {
  const index = Math.max(0, variants.findIndex((variant) => variant.key === current))
  const by = (step: number) => go(variants[(index + step + variants.length) % variants.length].key, param)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target.closest('input, textarea, select, [contenteditable]')) return
      if (event.key === keys[0]) by(-1)
      if (event.key === keys[1]) by(1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
  if (!import.meta.env.DEV) return null
  const button = 'size-7 rounded-full hover:bg-white/15 cursor-pointer'
  return (
    <div
      style={{ bottom: 16 + stack * 48 }}
      className="fixed left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-black px-2 py-1.5 font-mono text-xs text-white shadow-2xl ring-2 ring-fuchsia-500">
      <button type="button" className={button} onClick={() => by(-1)} aria-label="Previous variant">
        ‹
      </button>
      <span className="min-w-56 text-center">
        PROTOTYPE · {variants[index].key} — {variants[index].name} <span className="text-white/50">{keys.join(' ')}</span>
      </span>
      <button type="button" className={button} onClick={() => by(1)} aria-label="Next variant">
        ›
      </button>
    </div>
  )
}

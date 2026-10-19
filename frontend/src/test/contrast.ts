// WCAG 2.x contrast of the theme's colours, as written in index.css (oklch). Used by the theme test only.

/** The custom properties set in one rule of the stylesheet, e.g. `:root`. */
export function variables(css: string, selector: string): Map<string, string> {
  const start = css.indexOf(`${selector} {`)
  if (start < 0) throw new Error(`no ${selector} rule`)
  const body = css.slice(start, css.indexOf('}', start))
  return new Map([...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((match) => [match[1], match[2].trim()]))
}

/** The relative luminance of an opaque `oklch(L C H)` colour, by way of OKLab and linear sRGB. */
export function luminance(colour: string): number {
  const match = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\)$/.exec(colour)
  if (!match) throw new Error(`not an opaque oklch colour: ${colour}`)
  const [lightness, chroma, hue] = match.slice(1).map(Number)
  const a = chroma * Math.cos((hue * Math.PI) / 180)
  const b = chroma * Math.sin((hue * Math.PI) / 180)
  const l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (lightness - 0.0894841775 * a - 1.291485548 * b) ** 3
  // Clipped to the sRGB gamut, as a browser shows it.
  const clip = (value: number) => Math.min(1, Math.max(0, value))
  const red = clip(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s)
  const green = clip(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s)
  const blue = clip(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s)
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue
}

/** The contrast ratio of two colours, from 1 to 21. */
export function contrast(first: string, second: string): number {
  const [light, dark] = [luminance(first), luminance(second)].sort((x, y) => y - x)
  return (light + 0.05) / (dark + 0.05)
}

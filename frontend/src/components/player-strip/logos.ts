// A model's icon in its player strip: its family's logo (LobeHub Icons, MIT; see assets/logos/LICENSE), else a
// monogram in a colour fixed per family.
import deepseek from '@/assets/logos/deepseek.svg'
import gemma from '@/assets/logos/gemma.svg'
import meta from '@/assets/logos/meta.svg'
import mistral from '@/assets/logos/mistral.svg'
import qwen from '@/assets/logos/qwen.svg'

export type ModelIcon = { logo: string; family: string } | { monogram: string; colour: string }

/** The families with a logo, by the family as the Ollama name spells it. */
const LOGOS: Record<string, { logo: string; family: string }> = {
  qwen: { logo: qwen, family: 'Qwen' },
  llama: { logo: meta, family: 'Meta' },
  gemma: { logo: gemma, family: 'Gemma' },
  mistral: { logo: mistral, family: 'Mistral' },
  ministral: { logo: mistral, family: 'Mistral' },
  deepseek: { logo: deepseek, family: 'DeepSeek' },
}

/** The monograms' colours, each dark enough for white text to pass WCAG AA on it. */
const MONOGRAM_COLOURS = ['#6b4f8a', '#3c6585', '#2e7466', '#a14b24', '#3d55a8', '#55702f', '#3a3a3a', '#8a3f5c']

/**
 * The model's family: its name without a registry path, up to its version or first separator, e.g. "qwen" for
 * "qwen3.5:9b", "gemma" for "hf.co/unsloth/gemma-3-4b-it-GGUF:Q4_K_M".
 */
function family(model: string): string {
  const name = model.split('/').at(-1)!.split(':')[0].toLowerCase()
  return name.match(/^[a-z]+/)?.[0] ?? name
}

export function modelIcon(model: string): ModelIcon {
  const name = family(model)
  const logo = LOGOS[name]
  if (logo) return logo
  // The same family always hashes to the same colour.
  const hash = [...name].reduce((sum, char) => (sum * 31 + char.charCodeAt(0)) >>> 0, 0)
  return { monogram: (name.charAt(0) || '?').toUpperCase(), colour: MONOGRAM_COLOURS[hash % MONOGRAM_COLOURS.length] }
}

import { expect, test } from 'vitest'
import { modelIcon } from '@/components/player-strip/logos'

const logoOf = (model: string) => {
  const icon = modelIcon(model)
  return 'logo' in icon ? icon.family : null
}

test('qwen, llama, gemma, mistral and deepseek models show their family logo, matched on the name before the version', () => {
  expect(logoOf('qwen3.5:9b')).toBe('Qwen')
  expect(logoOf('qwen2.5-coder:7b')).toBe('Qwen')
  expect(logoOf('llama3.2:3b')).toBe('Meta')
  expect(logoOf('gemma3:4b')).toBe('Gemma')
  expect(logoOf('mistral-small:24b')).toBe('Mistral')
  expect(logoOf('ministral-3:8b')).toBe('Mistral')
  expect(logoOf('deepseek-r1:8b')).toBe('DeepSeek')
  expect(logoOf('Qwen3:latest')).toBe('Qwen')
})

test('a family without a logo gets a monogram, in the same colour for every model of the family', () => {
  expect(modelIcon('phi4-mini:3.8b')).toMatchObject({ monogram: 'P' })
  expect(modelIcon('gpt-oss:20b')).toMatchObject({ monogram: 'G' })
  expect(modelIcon('smollm2:1.7b')).toMatchObject({ monogram: 'S' })
  const colour = (model: string) => (modelIcon(model) as { colour: string }).colour
  expect(colour('phi4-mini:3.8b')).toBe(colour('phi3:14b'))
  expect(colour('phi4-mini:3.8b')).not.toBe(colour('gpt-oss:20b'))
})

test('a model pulled from a registry path is matched on its own name', () => {
  expect(logoOf('hf.co/unsloth/gemma-3-4b-it-GGUF:Q4_K_M')).toBe('Gemma')
})

test('a model whose name is not the family it says it is gets no family logo', () => {
  // "qwenlike" is not qwen: the family is the name up to its version or first separator.
  expect(logoOf('qwenlike:1b')).toBeNull()
})

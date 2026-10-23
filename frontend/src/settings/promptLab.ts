// Prompt lab (CONTEXT.md): the tools for experimenting with prompts, starting with each LLM side's Prompt template in
// the New game sheet. A Preference like Move sound, kept in this browser across games and reloads, off until switched
// on. It changes which tools are shown, never how a game is played: off, every side plays its default Prompt template.
import { useSyncExternalStore } from 'react'

const PROMPT_LAB_KEY = 'chessllm.promptLab'

const listeners = new Set<() => void>()

export function isPromptLabOn(): boolean {
  return localStorage.getItem(PROMPT_LAB_KEY) === 'on'
}

export function setPromptLabOn(on: boolean) {
  localStorage.setItem(PROMPT_LAB_KEY, on ? 'on' : 'off')
  for (const listener of listeners) listener()
}

const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Whether Prompt lab is on, the component shown again whenever it is switched. */
export const usePromptLab = () => useSyncExternalStore(subscribe, isPromptLabOn)

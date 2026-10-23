// Prompt templates as GET /api/prompt-templates lists them, for the tests.
import type { PromptTemplateInfo } from '@/api/types'

export const FREE: PromptTemplateInfo['fits'] = ['free', 'blind_enforced']
export const LISTED: PromptTemplateInfo['fits'] = ['listed', 'listed_enforced']
/** The Turn memories whose turns show the position, which every template but Moves fits. */
export const POSITION: PromptTemplateInfo['turn_memories'] = ['fresh', 'chat_position']

/** What a template is the Default of: each pair of the LLM constraints and Turn memories. */
export const defaultsOf = (
  constraints: PromptTemplateInfo['fits'],
  memories: PromptTemplateInfo['turn_memories'],
): PromptTemplateInfo['default_for'] =>
  constraints.flatMap((llm_constraints) => memories.map((turn_memory) => ({ llm_constraints, turn_memory })))

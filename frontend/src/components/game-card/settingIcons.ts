// The Lucide icon of each setting value the Game card shows (DESIGN.md: Game card).
import {
  Brain,
  ChessKnight,
  Eye,
  Flag,
  Lightbulb,
  ListChecks,
  Lock,
  MessageSquare,
  MessageSquareText,
  Repeat,
  ShieldCheck,
  Zap,
  type LucideProps,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { BrainOff } from '@/components/icons/BrainOff'
import type { GameSetting } from '@/game/wording'

type IconOf = ComponentType<LucideProps>

const ICONS: { [setting in GameSetting['setting']]: Record<string, IconOf> } = {
  llm_constraints: { free: Eye, listed: ListChecks, blind_enforced: Lock, listed_enforced: ShieldCheck },
  rules: { standard: ChessKnight, chaos: Zap },
  retry_feedback: { explained: MessageSquareText, bare: MessageSquare, hinted: Lightbulb, repeat: Repeat },
  thinking: { on: Brain, off: BrainOff },
  max_attempts: {},
}

/** A setting's icon; the forfeit limit is a `Flag` whatever the number. */
export const settingIcon = ({ setting, value }: Pick<GameSetting, 'setting' | 'value'>): IconOf =>
  setting === 'max_attempts' ? Flag : ICONS[setting][value]

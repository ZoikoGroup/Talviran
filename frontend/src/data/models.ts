/**
 * Selectable models.
 *
 * Presentation only for now — the AI gateway (docs/AI-001) isn't wired up, so
 * the choice is recorded on the message and shown in the transcript rather
 * than changing how a reply is produced.
 */

export type ModelId = 'talvrin-go' | 'talvrin-pro'

export interface Model {
  id: ModelId
  /** Tailwind class for the status dot, so the tiers read apart at a glance. */
  dot: string
  blurb: string
}

export const MODELS: Model[] = [
  {
    id: 'talvrin-go',
    dot: 'bg-fresh',
    blurb: 'Fast answers for everyday lookups and conventions.',
  },
  {
    id: 'talvrin-pro',
    dot: 'bg-primary',
    blurb: 'Deeper evidence chains and multi-step calculations.',
  },
]

export const DEFAULT_MODEL: ModelId = 'talvrin-go'

export const getModel = (id: ModelId): Model =>
  MODELS.find((m) => m.id === id) ?? MODELS[0]

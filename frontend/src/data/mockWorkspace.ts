/**
 * Seed history for the UI prototype.
 *
 * There is no backend yet (see docs/API-001), so a first-run workspace would
 * otherwise be a single empty chat — which shows none of the sidebar's real
 * behaviour: date bucketing, projects, or chats nested under a project.
 *
 * These seeds only ever populate an *empty* workspace. Once anything real is
 * in localStorage they are never applied again, so they can't overwrite work.
 * Replies are produced by `buildReply` rather than written out here, so the
 * seeded conversations stay in step with the canned reply logic — including
 * the recommendation-safe redirect (PRD-001 §11).
 */

import { buildReply, type ChatMessage } from '@/data/mockReply'

export interface MockProject {
  id: string
  name: string
}

export interface MockChat {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: number
  projectId: string | null
}

const HOUR = 3_600_000

const PROJECTS: MockProject[] = [
  { id: 'seed-gilt-curve', name: 'Gilt curve review' },
  { id: 'seed-ust-monitoring', name: 'US Treasury monitoring' },
  { id: 'seed-q3-pack', name: 'Client Q3 evidence pack' },
]

interface Seed {
  ask: string
  /** Hours before now, so the chats land across every history bucket. */
  hoursAgo: number
  projectId?: string
  followUp?: string
}

const SEEDS: Seed[] = [
  // ---- Today ----
  { ask: 'What are the terms of the 4¼% Treasury Gilt 2036?', hoursAgo: 0.4 },
  {
    ask: 'Explain accrued interest and the ex-dividend window',
    hoursAgo: 3,
    followUp: 'Show the clean and dirty price for a 12 Sep settlement',
  },
  {
    ask: 'Day count conventions across the gilt curve',
    hoursAgo: 6,
    projectId: 'seed-gilt-curve',
  },

  // ---- Yesterday ----
  { ask: 'Should I buy the 2036 gilt?', hoursAgo: 30 },
  {
    ask: 'Alert me when the 10y Treasury yield moves 25bp',
    hoursAgo: 34,
    projectId: 'seed-ust-monitoring',
  },

  // ---- Previous 7 days ----
  { ask: 'Compare the 10y gilt and the 10y Treasury', hoursAgo: 76 },
  {
    ask: 'Roll-down on the 5y point of the gilt curve',
    hoursAgo: 110,
    projectId: 'seed-gilt-curve',
  },
  { ask: 'Which vendor observations disagree on the 2036 close?', hoursAgo: 140 },

  // ---- Previous 30 days ----
  {
    ask: 'Build an evidence bundle for the Q3 gilt review',
    hoursAgo: 288,
    projectId: 'seed-q3-pack',
  },
  { ask: 'How are conflicting source observations reconciled?', hoursAgo: 432 },
  { ask: 'What is the ex-dividend period for gilts?', hoursAgo: 600 },

  // ---- Older ----
  { ask: 'Coverage proof for a monitoring rule that stopped firing', hoursAgo: 1080 },
]

const exchange = (ask: string): ChatMessage[] => [
  { role: 'user', text: ask },
  { role: 'assistant', ...buildReply(ask) },
]

export const mockProjects = (): MockProject[] => PROJECTS.map((p) => ({ ...p }))

export const mockChats = (): MockChat[] =>
  SEEDS.map((seed, i) => ({
    id: `seed-chat-${i}`,
    // Titled the same way a real first message titles a chat.
    title: seed.ask.slice(0, 40),
    messages: seed.followUp
      ? [...exchange(seed.ask), ...exchange(seed.followUp)]
      : exchange(seed.ask),
    createdAt: Date.now() - seed.hoursAgo * HOUR,
    projectId: seed.projectId ?? null,
  }))

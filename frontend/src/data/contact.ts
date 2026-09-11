/** Single source for how to reach us, so pages can't drift apart. */
export const SUPPORT_EMAIL = 'talvrin@zoikogroup.com'

export const CONTACT_TOPICS = [
  'Product question',
  'Data or source query',
  'Report an incorrect figure',
  'Account and access',
  'Partnership or enterprise',
  'Privacy request',
  'Something else',
] as const

export type ContactTopic = (typeof CONTACT_TOPICS)[number]

/**
 * Composes a mailto: link. There is no form endpoint yet, and a form that
 * silently swallowed a message would be worse than one that hands it to the
 * user's mail client.
 */
export function mailtoLink(topic: string, name: string, message: string) {
  const subject = `Talvrin — ${topic}`
  const body = [message.trim(), '', '—', name.trim()].filter(Boolean).join('\n')
  return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(
    subject
  )}&body=${encodeURIComponent(body)}`
}

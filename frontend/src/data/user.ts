/**
 * The signed-in user, for the UI prototype.
 *
 * Hardcoded until identity lands (the backend's identity module is in place,
 * but the frontend isn't wired to it yet). Kept in one place so the sidebar
 * footer and the hero greeting can't drift apart.
 */

export const currentUser = {
  name: 'Vignesh K.',
  /** Used for the greeting — a full name reads oddly after "Hello,". */
  firstName: 'Vignesh',
  initials: 'VK',
  plan: 'FREE',
} as const

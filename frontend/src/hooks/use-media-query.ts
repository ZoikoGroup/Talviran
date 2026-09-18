import { useEffect, useState } from 'react'

/**
 * Tracks a CSS media query, the same lazy-init + change-listener shape as
 * useReducedMotion. Used to keep a handful of JS decisions (tab order,
 * whether the sidebar behaves as a drawer) in step with the CSS breakpoints
 * driving everything else, rather than duplicating a pixel value that could
 * drift from tailwind.config's `lg`.
 */
export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches
  )

  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = () => setMatches(mq.matches)
    onChange()
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])

  return matches
}

/** Tailwind's default `lg` breakpoint (1024px) — the point at which the
 * sidebar switches from a permanent column to an off-canvas drawer. */
export function useIsDesktop() {
  return useMediaQuery('(min-width: 1024px)')
}

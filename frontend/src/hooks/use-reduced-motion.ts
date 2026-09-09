import { useEffect, useState } from 'react'

/**
 * Tracks the user's `prefers-reduced-motion` setting.
 *
 * The Orb background runs a continuous requestAnimationFrame loop on the GPU,
 * so we skip mounting it entirely when a user has asked for reduced motion and
 * fall back to the static CSS glow instead.
 */
export function useReducedMotion() {
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  return reduced
}

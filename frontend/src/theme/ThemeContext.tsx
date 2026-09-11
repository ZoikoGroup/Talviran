import { createContext, useContext, useEffect, useMemo, useState } from 'react'

export type Theme = 'dark' | 'light'

interface ThemeValue {
  theme: Theme
  setTheme: (t: Theme) => void
}

const ThemeContext = createContext<ThemeValue | null>(null)

/**
 * Owns the `.light` class on <html>.
 *
 * This used to live inside the chat shell, which was fine while that was the
 * only screen. Now that sign-in and the rest render outside it, the theme has
 * to be applied above the router or those pages paint in the wrong palette.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem('talvrin-theme') as Theme) || 'dark'
  )

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    try {
      localStorage.setItem('talvrin-theme', theme)
    } catch {
      // Private mode — the choice just won't persist.
    }
  }, [theme])

  const value = useMemo(() => ({ theme, setTheme }), [theme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}

import { useEffect } from 'react'
import { ArrowLeft, Moon, Sun } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SettingsPageProps {
  onBack: () => void
  theme: 'dark' | 'light'
  onThemeChange: (theme: 'dark' | 'light') => void
}

const THEMES = [
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'light', label: 'Light', Icon: Sun },
] as const

export default function SettingsPage({
  onBack,
  theme,
  onThemeChange,
}: SettingsPageProps) {
  // Escape is the only keyboard way out of a full-pane view.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onBack()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onBack])

  return (
    <div className="scrollbar-slim flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-6 pb-16 pt-8">
        <div className="mb-7 flex items-center gap-3">
          <button
            onClick={onBack}
            aria-label="Back"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <ArrowLeft className="h-[18px] w-[18px]" />
          </button>
          <h1 className="text-[22px] font-semibold tracking-tight">Settings</h1>
        </div>

        <section>
          <h2 className="mb-2.5 text-[10.5px] font-semibold uppercase tracking-widest text-muted-foreground">
            Appearance
          </h2>

          <div className="rounded-xl border border-border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-4">
              <div className="min-w-0">
                <div className="text-[14px] font-medium">Theme</div>
                <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">
                  Applies across the app and is remembered on this device.
                </p>
              </div>

              <div
                role="radiogroup"
                aria-label="Theme"
                className="flex shrink-0 gap-1 rounded-full bg-secondary p-1"
              >
                {THEMES.map(({ value, label, Icon }) => (
                  <button
                    key={value}
                    role="radio"
                    aria-checked={theme === value}
                    onClick={() => onThemeChange(value)}
                    className={cn(
                      'flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12.5px] transition-colors',
                      theme === value
                        ? 'bg-card font-medium text-foreground ring-1 ring-inset ring-border'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

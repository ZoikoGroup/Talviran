'use client'

import { useRef, useCallback, useEffect } from 'react'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  ArrowUpIcon,
  Paperclip,
  Landmark,
  Calculator,
  Scale,
  BellRing,
  FileSearch,
  BookOpen,
  ShieldCheck,
  FileUp,
} from 'lucide-react'

/* ------------------------------------------------------------------
   Auto-resizing textarea
   ------------------------------------------------------------------ */

interface AutoResizeProps {
  minHeight: number
  maxHeight?: number
}

function useAutoResizeTextarea({ minHeight, maxHeight }: AutoResizeProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current
      if (!textarea) return

      if (reset) {
        textarea.style.height = `${minHeight}px`
        return
      }

      textarea.style.height = `${minHeight}px` // reset first
      const newHeight = Math.max(
        minHeight,
        Math.min(textarea.scrollHeight, maxHeight ?? Infinity)
      )
      textarea.style.height = `${newHeight}px`
    },
    [minHeight, maxHeight]
  )

  useEffect(() => {
    if (textareaRef.current) textareaRef.current.style.height = `${minHeight}px`
  }, [minHeight])

  return { textareaRef, adjustHeight }
}

/* ------------------------------------------------------------------
   Quick actions — each seeds a real Talvrin research prompt
   ------------------------------------------------------------------ */

const QUICK_ACTIONS = [
  { icon: Landmark, label: 'Explain an instrument', prompt: 'Explain the 4¼% Treasury Gilt 2036' },
  { icon: Calculator, label: 'Run a calculation', prompt: 'What is accrued interest on a gilt?' },
  { icon: Scale, label: 'Compare', prompt: 'Compare a 10-year gilt vs a 10-year US Treasury' },
  { icon: BellRing, label: 'Set an alert', prompt: 'Alert me if a gilt yield crosses 4.5%' },
  { icon: FileSearch, label: 'Search documents', prompt: 'Find the latest UK DMO gilt operations notice' },
  { icon: BookOpen, label: 'Market conventions', prompt: 'How does ACT/ACT (ICMA) day count work?' },
  { icon: ShieldCheck, label: 'Evidence trail', prompt: 'Show me the evidence chain for a gilt price' },
  { icon: FileUp, label: 'Upload a document', prompt: 'I want to ask questions about a prospectus' },
]

interface QuickActionProps {
  icon: React.ReactNode
  label: string
  onClick: () => void
}

function QuickAction({ icon, label, onClick }: QuickActionProps) {
  return (
    <Button
      variant="outline"
      onClick={onClick}
      className={cn(
        'h-9 gap-2 rounded-full border-border/70 bg-card/50 px-3.5',
        'text-muted-foreground backdrop-blur-sm transition-all',
        'hover:-translate-y-0.5 hover:border-border hover:bg-accent hover:text-foreground'
      )}
    >
      {icon}
      <span className="text-xs font-medium">{label}</span>
    </Button>
  )
}

/* ------------------------------------------------------------------
   Hero
   ------------------------------------------------------------------ */

interface TalvrinMoonChatProps {
  value: string
  onChange: (v: string) => void
  onSend: (text?: string) => void
  disabled?: boolean
}

export default function TalvrinMoonChat({
  value,
  onChange,
  onSend,
  disabled,
}: TalvrinMoonChatProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 52,
    maxHeight: 180,
  })

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
      adjustHeight(true)
    }
  }

  return (
    <div className="relative flex h-full w-full flex-col items-center overflow-hidden">
      {/* Aurora arc + vignette (pure CSS, theme-aware) */}
      <div className="moon-glow animate-glow-pulse" />
      <div className="hero-vignette" />

      {/* Title */}
      <div className="relative z-10 flex w-full flex-1 flex-col items-center justify-center px-6">
        <div className="animate-rise text-center">
          <h1 className="text-[2.75rem] font-semibold leading-none tracking-tight text-foreground">
            Talvrin
          </h1>
          <p className="mx-auto mt-4 max-w-md text-[15px] leading-relaxed text-muted-foreground">
            Source-linked research for public markets — ask anything below.
          </p>
        </div>
      </div>

      {/* Composer */}
      <div className="relative z-10 mb-[14vh] w-full max-w-3xl px-6">
        <div
          className={cn(
            'relative rounded-2xl border border-border/80 bg-card/70 backdrop-blur-xl',
            'shadow-2xl shadow-black/40 transition-colors',
            'focus-within:border-ring/60'
          )}
        >
          <Textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              onChange(e.target.value)
              adjustHeight()
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask about an instrument, convention or calculation…"
            className={cn(
              'w-full resize-none border-none bg-transparent px-4 pt-4',
              'text-[15px] text-foreground',
              'focus-visible:ring-0 focus-visible:ring-offset-0',
              'placeholder:text-muted-foreground/70'
            )}
            style={{ overflow: 'hidden' }}
          />

          <div className="flex items-center justify-between px-3 pb-3">
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9 text-muted-foreground hover:text-foreground"
              title="Attach a document"
            >
              <Paperclip className="h-4 w-4" />
              <span className="sr-only">Attach a document</span>
            </Button>

            <Button
              size="icon"
              onClick={() => {
                onSend()
                adjustHeight(true)
              }}
              disabled={disabled || !value.trim()}
              className={cn(
                'h-9 w-9 rounded-xl transition-transform',
                'bg-gradient-to-br from-indigo-500 to-purple-500 text-white',
                'hover:scale-105 active:scale-95',
                'disabled:bg-secondary disabled:from-secondary disabled:to-secondary disabled:text-muted-foreground'
              )}
            >
              <ArrowUpIcon className="h-4 w-4" />
              <span className="sr-only">Send</span>
            </Button>
          </div>
        </div>

        {/* Quick actions */}
        <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5">
          {QUICK_ACTIONS.map(({ icon: Ico, label, prompt }) => (
            <QuickAction
              key={label}
              icon={<Ico className="h-4 w-4" />}
              label={label}
              onClick={() => onSend(prompt)}
            />
          ))}
        </div>

        <p className="mt-6 text-center text-[11.5px] leading-relaxed text-muted-foreground/70">
          Source-linked facts and reproducible calculations.{' '}
          <span className="font-medium text-muted-foreground">
            Talvrin does not give investment advice.
          </span>{' '}
          Prototype — no backend connected.
        </p>
      </div>
    </div>
  )
}

'use client'

import { useRef, useCallback, useEffect } from 'react'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import Orb from '@/components/ui/orb'
import { useReducedMotion } from '@/hooks/use-reduced-motion'
import { cn } from '@/lib/utils'
import { ArrowUpIcon } from 'lucide-react'
import { currentUser } from '@/data/user'
import AttachMenu, { AttachmentChips } from '@/components/AttachMenu'
import ModelSwitcher from '@/components/ModelSwitcher'
import type { ModelId } from '@/data/models'

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
   Hero
   ------------------------------------------------------------------ */

/** Matches the --background token per theme so the Orb shader blends. */
const ORB_BG = { dark: '#08080b', light: '#fcfcfe' } as const

interface TalvrinMoonChatProps {
  value: string
  onChange: (v: string) => void
  onSend: (text?: string) => void
  disabled?: boolean
  theme?: 'dark' | 'light'
  attachments: File[]
  onAttach: (files: File[]) => void
  onRemoveAttachment: (index: number) => void
  model: ModelId
  onModelChange: (id: ModelId) => void
}

export default function TalvrinMoonChat({
  value,
  onChange,
  onSend,
  disabled,
  theme = 'dark',
  attachments,
  onAttach,
  onRemoveAttachment,
  model,
  onModelChange,
}: TalvrinMoonChatProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 36,
    maxHeight: 160,
  })
  const reducedMotion = useReducedMotion()
  const isLight = theme === 'light'

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
      adjustHeight(true)
    }
  }

  return (
    <div className="relative flex h-full w-full flex-col items-center justify-center overflow-hidden">
      {/* ---------- Background ----------
          Sized off the container's own height (not vh) and kept square, so the
          orb always sits fully inside the visible area whatever the sidebar
          is doing. The wrapper clips anything that still overhangs. */}
      {reducedMotion ? (
        <>
          <div className="moon-glow" />
          <div className="hero-vignette" />
        </>
      ) : (
        <div
          aria-hidden="true"
          className={cn(
            'absolute left-1/2 top-1/2 aspect-square h-[78%] max-w-[92%]',
            '-translate-x-1/2 -translate-y-1/2',
            isLight ? 'opacity-40' : 'opacity-90'
          )}
        >
          <Orb
            hue={255}
            hoverIntensity={0.45}
            rotateOnHover
            forceHoverState={false}
            backgroundColor={ORB_BG[theme]}
          />
        </div>
      )}

      {/* ---------- Greeting + composer, centred as one block ---------- */}
      <div className="relative z-10 flex w-full max-w-3xl flex-col px-6">
        <div className="animate-rise pointer-events-none text-center">
          <h1
            className={cn(
              'text-[2.75rem] font-semibold leading-none tracking-tight text-foreground',
              !isLight && '[text-shadow:0_2px_28px_rgba(0,0,0,0.55)]'
            )}
          >
            Hello, {currentUser.firstName}
          </h1>
          <p
            className={cn(
              'mx-auto mt-4 max-w-md text-[15px] leading-relaxed',
              isLight
                ? 'text-muted-foreground'
                : 'text-muted-foreground [text-shadow:0_1px_16px_rgba(0,0,0,0.6)]'
            )}
          >
            Source-linked research for public markets.
          </p>
        </div>

        {/* ---------- Composer ---------- */}
        <div className="mt-9 w-full">
        <AttachmentChips files={attachments} onRemove={onRemoveAttachment} />

        {/* A single slim row. `rounded-[26px]` reads as a pill at one line
            and stays sensible once the textarea grows. */}
        <div
          data-composer-bar
          className={cn(
            'relative flex items-end gap-1.5 rounded-[26px] border px-2 py-2',
            'backdrop-blur-2xl transition-colors focus-within:border-ring/60',
            isLight
              ? 'border-border bg-card/95 shadow-xl shadow-slate-900/10'
              : 'border-border/80 bg-card/75 shadow-2xl shadow-black/50'
          )}
        >
          <AttachMenu onFiles={onAttach} disabled={disabled} />

          <Textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => {
              onChange(e.target.value)
              adjustHeight()
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask about an instrument, convention or calculation…"
            className={cn(
              'min-h-0 flex-1 resize-none border-none bg-transparent px-1 py-1.5',
              'text-[15px] leading-6 text-foreground',
              'focus-visible:ring-0 focus-visible:ring-offset-0',
              'placeholder:text-muted-foreground/70'
            )}
            style={{ overflow: 'hidden' }}
          />

          <ModelSwitcher value={model} onChange={onModelChange} disabled={disabled} />

          <Button
            size="icon"
            onClick={() => {
              onSend()
              adjustHeight(true)
            }}
            disabled={disabled || !value.trim()}
            className={cn(
              'h-9 w-9 shrink-0 rounded-full transition-transform',
              'bg-gradient-to-br from-indigo-500 to-purple-500 text-white',
              'hover:scale-105 active:scale-95',
              'disabled:bg-secondary disabled:from-secondary disabled:to-secondary disabled:text-muted-foreground'
            )}
          >
            <ArrowUpIcon className="h-4 w-4" />
            <span className="sr-only">Send</span>
          </Button>
        </div>

          <p
            className={cn(
              'mt-5 text-center text-[11.5px] leading-relaxed',
              isLight ? 'text-muted-foreground' : 'text-muted-foreground/70'
            )}
          >
            Source-linked facts and reproducible calculations.{' '}
            <span className="font-medium text-foreground/80">
              Talvrin does not give investment advice.
            </span>{' '}
            Prototype — no backend connected.
          </p>
        </div>
      </div>
    </div>
  )
}

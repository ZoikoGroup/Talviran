'use client'

import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import Orb from '@/components/ui/orb'
import { useReducedMotion } from '@/hooks/use-reduced-motion'
import { useAutoResizeTextarea } from '@/hooks/use-auto-resize-textarea'
import { useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import { ArrowUpIcon, Tag, Sparkles, X } from 'lucide-react'
import { useCurrentUser } from '@/data/user'
import AttachMenu, { AttachmentChips } from '@/components/AttachMenu'
import ModelSwitcher from '@/components/ModelSwitcher'
import type { ModelId } from '@/data/models'
import type { TaggedAsset } from '@/data/mockReply'

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
  taggedAsset?: TaggedAsset | null
  onRemoveTaggedAsset?: () => void
  onOpenSearch?: () => void
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
  taggedAsset,
  onRemoveTaggedAsset,
  onOpenSearch,
}: TalvrinMoonChatProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 36,
    maxHeight: 160,
  })
  const reducedMotion = useReducedMotion()
  const currentUser = useCurrentUser()
  const isLight = theme === 'light'
  // The full sentence wraps the composer's textarea rather than the pill,
  // so a narrow viewport gets the shorter form before that ever happens.
  const isNarrow = !useMediaQuery('(min-width: 400px)')
  const placeholder = taggedAsset
    ? `Ask anything about ${taggedAsset.name || taggedAsset.symbol}… (trusted sources only)`
    : isNarrow
    ? 'Ask a question…'
    : 'Ask about an instrument, convention or calculation…'

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
      adjustHeight(true)
    }
  }

  const suggestedPrompts = taggedAsset
    ? [
        `What are the primary yield drivers & rate path expectations for ${taggedAsset.symbol}?`,
        `Analyze market structure, auction stats & duration risk for ${taggedAsset.name}`,
        `Compare ${taggedAsset.symbol} benchmark with sovereign spreads and curve shape`,
        `Explain sensitivity to central bank policy and inflation data`,
      ]
    : []

  return (
    <div className="relative flex h-full w-full flex-col items-center justify-center overflow-hidden">
      {/* ---------- Background ---------- */}
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

      {/* ---------- Greeting / Tagged Asset + composer ---------- */}
      <div className="relative z-10 flex w-full max-w-3xl flex-col px-4 sm:px-6">
        <div className="animate-rise pointer-events-none text-center">
          {taggedAsset ? (
            <>
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-[11.5px] font-semibold text-primary mb-3">
                <Tag className="h-3 w-3" />
                <span>Tagged Market Context</span>
              </div>
              <h1
                className={cn(
                  'text-[2rem] font-bold leading-tight tracking-tight text-foreground sm:text-[2.5rem]',
                  !isLight && '[text-shadow:0_2px_28px_rgba(0,0,0,0.55)]'
                )}
              >
                {taggedAsset.name}
              </h1>
              <p
                className={cn(
                  'mx-auto mt-2.5 max-w-lg text-[14px] leading-relaxed',
                  isLight
                    ? 'text-muted-foreground'
                    : 'text-muted-foreground [text-shadow:0_1px_16px_rgba(0,0,0,0.6)]'
                )}
              >
                <span className="font-mono text-primary font-medium">{taggedAsset.symbol}</span>
                {taggedAsset.assetClass && ` • ${taggedAsset.assetClass}`}
                {taggedAsset.price && ` • Last / Yield: ${taggedAsset.price}`}
                {taggedAsset.source && ` • Source: ${taggedAsset.source}`}
              </p>
            </>
          ) : (
            <>
              <h1
                className={cn(
                  'text-[2.25rem] font-semibold leading-none tracking-tight text-foreground sm:text-[2.75rem]',
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
            </>
          )}
        </div>

        {/* ---------- Composer ---------- */}
        <div className="mt-8 w-full">
          <AttachmentChips files={attachments} onRemove={onRemoveAttachment} />

          {/* Tagged Asset Chip above Composer */}
          {taggedAsset && (
            <div className="mb-2.5 flex items-center justify-between rounded-xl border border-primary/25 bg-card/85 px-3.5 py-2 shadow-sm backdrop-blur-md animate-in fade-in slide-in-from-bottom-1">
              <div className="flex items-center gap-2 min-w-0">
                <span className="grid h-5 w-5 place-items-center rounded-md bg-primary/20 text-primary shrink-0">
                  <Tag className="h-3 w-3" />
                </span>
                <span className="text-[12px] font-semibold text-foreground truncate">{taggedAsset.name}</span>
                <span className="font-mono text-[11px] text-primary shrink-0">({taggedAsset.symbol})</span>
                {taggedAsset.price && (
                  <span className="hidden sm:inline-block rounded bg-secondary px-1.5 py-0.5 font-mono text-[10.5px] text-foreground/80">
                    {taggedAsset.price}
                  </span>
                )}
              </div>
              {onRemoveTaggedAsset && (
                <button
                  type="button"
                  onClick={onRemoveTaggedAsset}
                  title="Remove tagged asset"
                  className="rounded-lg p-1 text-muted-foreground hover:bg-secondary hover:text-foreground transition ml-2"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}

          {/* A single slim row */}
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

            {onOpenSearch && !taggedAsset && (
              <button
                type="button"
                onClick={onOpenSearch}
                title="Tag an asset or search markets (⌘K)"
                disabled={disabled}
                className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground transition hover:bg-secondary hover:text-foreground active:scale-95 disabled:pointer-events-none cursor-pointer shrink-0"
              >
                <Tag className="h-4 w-4" />
              </button>
            )}

            <Textarea
              ref={textareaRef}
              rows={1}
              value={value}
              onChange={(e) => {
                onChange(e.target.value)
                adjustHeight()
              }}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
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
              disabled={disabled || (!value.trim() && !taggedAsset)}
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

          {/* Suggested Prompts for Tagged Asset */}
          {taggedAsset && (
            <div className="mt-3.5 flex flex-wrap items-center justify-center gap-1.5 animate-in fade-in">
              {suggestedPrompts.map((promptText, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    onChange(promptText)
                    onSend(promptText)
                  }}
                  className="inline-flex items-center gap-1.5 rounded-full border border-border/80 bg-secondary/50 hover:bg-secondary hover:border-primary/40 px-3 py-1.5 text-[11.5px] text-muted-foreground hover:text-foreground transition active:scale-95 text-left"
                >
                  <Sparkles className="h-3 w-3 text-primary shrink-0" />
                  <span className="truncate max-w-[280px] sm:max-w-none">{promptText}</span>
                </button>
              ))}
            </div>
          )}

          <p
            className={cn(
              'mt-5 text-center text-[11.5px] leading-relaxed',
              isLight ? 'text-muted-foreground' : 'text-muted-foreground/70'
            )}
          >
            Source-linked facts and reproducible calculations.{' '}
            <span className="font-medium text-foreground/80">
              Talvrin does not give investment advice.
            </span>
          </p>
        </div>
      </div>
    </div>
  )
}

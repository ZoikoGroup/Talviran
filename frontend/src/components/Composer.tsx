import { ArrowUpIcon, Tag, X } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { useAutoResizeTextarea } from '@/hooks/use-auto-resize-textarea'
import { useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import AttachMenu, { AttachmentChips } from '@/components/AttachMenu'
import ModelSwitcher from '@/components/ModelSwitcher'
import type { ModelId } from '@/data/models'
import type { TaggedAsset } from '@/data/mockReply'

interface ComposerProps {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  disabled?: boolean
  attachments: File[]
  onAttach: (files: File[]) => void
  onRemoveAttachment: (index: number) => void
  model: ModelId
  onModelChange: (id: ModelId) => void
  /** True once this chat's backend conversation exists - its model tier is
   * fixed forever at that point (the backend reads it once, at creation),
   * so the picker must stop being changeable or it would silently lie
   * about which model is actually answering later messages. */
  modelLocked?: boolean
  taggedAsset?: TaggedAsset | null
  onRemoveTaggedAsset?: () => void
  onOpenSearch?: () => void
}

export default function Composer({
  value,
  onChange,
  onSend,
  disabled,
  attachments,
  onAttach,
  onRemoveAttachment,
  model,
  onModelChange,
  modelLocked,
  taggedAsset,
  onRemoveTaggedAsset,
  onOpenSearch,
}: ComposerProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 36,
    maxHeight: 200,
  })
  // Below this, "Ask a follow-up…" plus the model pill and send button
  // leaves too little room for the placeholder on one line.
  const isNarrow = !useMediaQuery('(min-width: 360px)')

  const placeholder = taggedAsset
    ? `Ask about ${taggedAsset.symbol}… (trusted sources only)`
    : isNarrow
    ? 'Ask…'
    : 'Ask a follow-up…'

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
      adjustHeight(true)
    }
  }

  return (
    <div className="shrink-0 px-3 pb-4 pt-2 sm:px-6">
      <div className="mx-auto max-w-3xl mb-1.5 flex flex-col gap-1.5">
        <AttachmentChips files={attachments} onRemove={onRemoveAttachment} />

        {/* Tagged Asset Chip */}
        {taggedAsset && (
          <div className="flex items-center gap-1.5 animate-in fade-in slide-in-from-bottom-1">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/15 px-3 py-1 text-[12px] font-medium text-foreground backdrop-blur-md shadow-xs">
              <Tag className="h-3 w-3 text-primary" />
              <span>{taggedAsset.name}</span>
              <span className="font-mono text-[11px] text-primary/90">({taggedAsset.symbol})</span>
              {taggedAsset.price && (
                <span className="rounded bg-secondary/80 px-1.5 py-0.2 font-mono text-[10px] text-foreground/80">
                  {taggedAsset.price}
                </span>
              )}
              {onRemoveTaggedAsset && (
                <button
                  type="button"
                  onClick={onRemoveTaggedAsset}
                  title="Remove tagged asset"
                  className="ml-0.5 rounded-full p-0.5 text-muted-foreground hover:bg-white/15 hover:text-foreground transition"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          </div>
        )}
      </div>

      <div
        data-composer-bar
        className={cn(
          'mx-auto flex max-w-3xl items-end gap-1 rounded-[26px] border border-border sm:gap-1.5',
          'bg-card/80 px-2 py-2 shadow-xl shadow-black/20 backdrop-blur-xl',
          'transition-colors focus-within:border-ring/60'
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
            'max-h-[200px] min-h-0 flex-1 resize-none border-none bg-transparent px-1 py-2',
            'text-[14.75px] leading-6',
            'focus-visible:ring-0 focus-visible:ring-offset-0',
            'placeholder:text-muted-foreground/70'
          )}
          style={{ overflow: 'hidden' }}
        />

        <span title={modelLocked ? "This chat's model is set for its whole conversation" : undefined}>
          <ModelSwitcher value={model} onChange={onModelChange} disabled={disabled || modelLocked} />
        </span>

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
            'disabled:from-secondary disabled:to-secondary disabled:text-muted-foreground'
          )}
        >
          <ArrowUpIcon className="h-4 w-4" />
          <span className="sr-only">Send</span>
        </Button>
      </div>

      <p className="mx-auto mt-2.5 max-w-3xl text-center text-[11.5px] leading-relaxed text-muted-foreground/70">
        Source-linked facts and reproducible calculations.{' '}
        <span className="font-medium text-muted-foreground">
          Talvrin does not give investment advice.
        </span>
      </p>
    </div>
  )
}

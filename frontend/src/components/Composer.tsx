import { ArrowUpIcon } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { useAutoResizeTextarea } from '@/hooks/use-auto-resize-textarea'
import { useMediaQuery } from '@/hooks/use-media-query'
import { cn } from '@/lib/utils'
import AttachMenu, { AttachmentChips } from '@/components/AttachMenu'
import ModelSwitcher from '@/components/ModelSwitcher'
import type { ModelId } from '@/data/models'

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
}: ComposerProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight: 36,
    maxHeight: 200,
  })
  // Below this, "Ask a follow-up…" plus the model pill and send button
  // leaves too little room for the placeholder on one line.
  const isNarrow = !useMediaQuery('(min-width: 360px)')

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
      adjustHeight(true)
    }
  }

  return (
    <div className="shrink-0 px-3 pb-4 pt-2 sm:px-6">
      <div className="mx-auto max-w-3xl">
        <AttachmentChips files={attachments} onRemove={onRemoveAttachment} />
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

        <Textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => {
            onChange(e.target.value)
            adjustHeight()
          }}
          onKeyDown={handleKeyDown}
          placeholder={isNarrow ? 'Ask…' : 'Ask a follow-up…'}
          className={cn(
            'max-h-[200px] min-h-0 flex-1 resize-none border-none bg-transparent px-1 py-2',
            'text-[14.75px] leading-6',
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
        </span>{' '}
        Prototype — no backend connected.
      </p>
    </div>
  )
}

import { useRef, useEffect } from 'react'
import { ArrowUpIcon, Paperclip } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ComposerProps {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  disabled?: boolean
}

export default function Composer({
  value,
  onChange,
  onSend,
  disabled,
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null)

  // Auto-grow the textarea with its content.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 200) + 'px'
  }, [value])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSend()
    }
  }

  return (
    <div className="shrink-0 px-6 pb-4 pt-2">
      <div
        className={cn(
          'mx-auto flex max-w-3xl items-end gap-1.5 rounded-2xl border border-border',
          'bg-card/80 p-2 shadow-xl shadow-black/20 backdrop-blur-xl',
          'transition-colors focus-within:border-ring/60'
        )}
      >
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 shrink-0 text-muted-foreground hover:text-foreground"
          title="Attach a document"
        >
          <Paperclip className="h-4 w-4" />
          <span className="sr-only">Attach a document</span>
        </Button>

        <Textarea
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a follow-up…"
          className={cn(
            'max-h-[200px] min-h-0 resize-none border-none bg-transparent px-1.5 py-2',
            'text-[14.75px] leading-relaxed',
            'focus-visible:ring-0 focus-visible:ring-offset-0',
            'placeholder:text-muted-foreground/70'
          )}
          style={{ overflow: 'hidden' }}
        />

        <Button
          size="icon"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          className={cn(
            'h-9 w-9 shrink-0 rounded-xl transition-transform',
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

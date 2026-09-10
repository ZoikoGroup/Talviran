import { useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import PopoverMenu from '@/components/ui/popover-menu'
import { MODELS, getModel, type ModelId } from '@/data/models'

interface ModelSwitcherProps {
  value: ModelId
  onChange: (id: ModelId) => void
  disabled?: boolean
}

const MENU_WIDTH = 268

/** The composer's model pill; PopoverMenu handles placement and dismissal. */
export default function ModelSwitcher({
  value,
  onChange,
  disabled,
}: ModelSwitcherProps) {
  const [at, setAt] = useState<{ anchor: DOMRect; clear: DOMRect | null } | null>(
    null
  )
  const active = getModel(value)

  return (
    <>
      <button
        type="button"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          if (at) return setAt(null)
          const bar = e.currentTarget.closest('[data-composer-bar]')
          setAt({
            anchor: e.currentTarget.getBoundingClientRect(),
            clear: bar?.getBoundingClientRect() ?? null,
          })
        }}
        disabled={disabled}
        aria-label={`Model: ${active.id}`}
        aria-haspopup="menu"
        aria-expanded={!!at}
        className={cn(
          'flex h-8 shrink-0 items-center gap-1.5 rounded-full px-2.5 transition-colors',
          'text-[12.5px] text-muted-foreground hover:bg-accent hover:text-foreground',
          'disabled:pointer-events-none disabled:opacity-50'
        )}
      >
        <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', active.dot)} />
        <span className="font-medium">{active.id}</span>
        <ChevronDown
          className={cn('h-3.5 w-3.5 transition-transform', at && 'rotate-180')}
        />
      </button>

      {at && (
        <PopoverMenu
          anchor={at.anchor}
          clear={at.clear}
          prefer="top"
          width={MENU_WIDTH}
          onClose={() => setAt(null)}
          className="border-border bg-popover"
        >
          {MODELS.map((m) => (
            <button
              key={m.id}
              role="menuitemradio"
              aria-checked={m.id === value}
              onClick={() => {
                onChange(m.id)
                setAt(null)
              }}
                className={cn(
                  'flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors',
                  m.id === value
                    ? 'bg-accent/60'
                    : 'hover:bg-accent hover:text-foreground'
                )}
              >
                <span
                  className={cn('mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full', m.dot)}
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-medium text-foreground">
                    {m.id}
                  </span>
                  <span className="mt-0.5 block text-[11.5px] leading-relaxed text-muted-foreground">
                    {m.blurb}
                  </span>
                </span>
                {m.id === value && (
                  <Check className="mt-[3px] h-3.5 w-3.5 shrink-0 text-foreground" />
                )}
              </button>
          ))}
        </PopoverMenu>
      )}
    </>
  )
}

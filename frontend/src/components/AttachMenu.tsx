import { useRef, useState } from 'react'
import { File as FileIcon, Image, Paperclip, Plus, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import PopoverMenu from '@/components/ui/popover-menu'

interface AttachMenuProps {
  onFiles: (files: File[]) => void
  disabled?: boolean
}

const MENU_WIDTH = 190

/**
 * The composer's `+` — opens a small menu offering a document or an image
 * picker. Positioning and dismissal are handled by PopoverMenu.
 */
export default function AttachMenu({ onFiles, disabled }: AttachMenuProps) {
  const [at, setAt] = useState<{ anchor: DOMRect; clear: DOMRect | null } | null>(
    null
  )
  const fileRef = useRef<HTMLInputElement>(null)
  const imageRef = useRef<HTMLInputElement>(null)

  const pick = (ref: React.RefObject<HTMLInputElement | null>) => {
    setAt(null)
    ref.current?.click()
  }

  const take = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (files.length) onFiles(files)
    // Reset so picking the same file twice still fires a change event.
    e.target.value = ''
  }

  const ITEMS = [
    { label: 'Upload files', Icon: Paperclip, ref: fileRef },
    { label: 'Upload images', Icon: Image, ref: imageRef },
  ]

  return (
    <>
      <input ref={fileRef} type="file" multiple hidden onChange={take} />
      <input
        ref={imageRef}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={take}
      />

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
        aria-label="Add files"
        aria-haspopup="menu"
        aria-expanded={!!at}
        title="Add files"
        className={cn(
          'grid h-9 w-9 shrink-0 place-items-center rounded-full transition-colors',
          'text-muted-foreground hover:bg-accent hover:text-foreground',
          'disabled:pointer-events-none disabled:opacity-50'
        )}
      >
        <Plus className="h-[18px] w-[18px]" />
      </button>

      {at && (
        <PopoverMenu
          anchor={at.anchor}
          clear={at.clear}
          prefer="top"
          width={MENU_WIDTH}
          align="start"
          onClose={() => setAt(null)}
          className="border-border bg-popover"
        >
          {ITEMS.map(({ label, Icon, ref }) => (
            <button
              key={label}
              role="menuitem"
              onClick={() => pick(ref)}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <Icon className="h-4 w-4 shrink-0 opacity-80" />
              {label}
            </button>
          ))}
        </PopoverMenu>
      )}
    </>
  )
}

/* ------------------------------------------------------------------
   Attachment chips — what the picker produced, sitting above the bar
   ------------------------------------------------------------------ */

const kb = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`

interface AttachmentChipsProps {
  files: File[]
  onRemove: (index: number) => void
}

export function AttachmentChips({ files, onRemove }: AttachmentChipsProps) {
  if (files.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-1.5">
      {files.map((f, i) => (
        <span
          key={`${f.name}-${i}`}
          className="flex max-w-[240px] items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[12px] text-muted-foreground"
        >
          {f.type.startsWith('image/') ? (
            <Image className="h-3.5 w-3.5 shrink-0 opacity-70" />
          ) : (
            <FileIcon className="h-3.5 w-3.5 shrink-0 opacity-70" />
          )}
          <span className="truncate text-foreground/90">{f.name}</span>
          <span className="shrink-0 tabular-nums opacity-60">{kb(f.size)}</span>
          <button
            type="button"
            onClick={() => onRemove(i)}
            aria-label={`Remove ${f.name}`}
            className="shrink-0 rounded-full p-0.5 transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  )
}

import { useId, useState } from 'react'
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FieldProps extends Omit<React.ComponentProps<'input'>, 'id'> {
  label: string
  /** Shown under the input and wired up via aria-describedby. */
  error?: string | null
  hint?: string
  /** Rendered at the right of the label row — e.g. a "Forgot password?" link. */
  action?: React.ReactNode
}

export function Field({
  label,
  error,
  hint,
  action,
  className,
  type,
  ...rest
}: FieldProps) {
  const id = useId()
  const [reveal, setReveal] = useState(false)
  const isPassword = type === 'password'
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined

  return (
    <div>
      {/* Label and its action share a row so the field below stays a clean
          rectangle — a link floating under the input pushes the next field
          out of rhythm. */}
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="text-[13px] font-medium leading-none">
          {label}
        </label>
        {action}
      </div>

      <div className="relative">
        <input
          id={id}
          type={isPassword && reveal ? 'text' : type}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={cn(
            // 44px tall: the minimum comfortable pointer target, and it stops
            // the form looking cramped next to the 26px heading.
            'h-11 w-full rounded-xl border bg-background/50 px-3.5 text-[14px]',
            'outline-none transition-[border-color,box-shadow,background-color] duration-150',
            'placeholder:text-muted-foreground/50',
            'hover:border-border/80',
            'focus:bg-background/80',
            error
              ? 'border-destructive/60 focus:border-destructive focus:ring-[3px] focus:ring-destructive/15'
              : 'border-border focus:border-ring/80 focus:ring-[3px] focus:ring-ring/15',
            'disabled:cursor-not-allowed disabled:opacity-60',
            isPassword && 'pr-11',
            className
          )}
          {...rest}
        />

        {isPassword && (
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setReveal((r) => !r)}
            aria-label={reveal ? 'Hide password' : 'Show password'}
            className="absolute right-1.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground/70 transition-colors hover:bg-accent hover:text-foreground"
          >
            {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>

      {error ? (
        <p
          id={`${id}-error`}
          className="mt-2 flex items-start gap-1.5 text-[12px] leading-snug text-destructive"
        >
          {/* The icon carries the meaning for anyone who can't distinguish the
              colour — red text alone is not an error indicator. */}
          <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-2 text-[12px] leading-snug text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

/** Full-width primary action, matching the composer's send button gradient. */
export function SubmitButton({
  children,
  busy,
  className,
  ...rest
}: React.ComponentProps<'button'> & { busy?: boolean }) {
  return (
    <button
      type="submit"
      disabled={busy || rest.disabled}
      aria-busy={busy}
      {...rest}
      className={cn(
        'relative inline-flex h-11 w-full items-center justify-center gap-2 rounded-xl',
        'text-[14px] font-medium text-white transition-all duration-150',
        'bg-gradient-to-br from-indigo-500 to-purple-500',
        'shadow-lg shadow-indigo-500/20',
        'hover:shadow-xl hover:shadow-indigo-500/25 hover:brightness-110',
        'active:scale-[0.99] active:shadow-md',
        'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40',
        'disabled:cursor-not-allowed disabled:opacity-70 disabled:shadow-none',
        'disabled:hover:brightness-100 disabled:active:scale-100',
        className
      )}
    >
      {/* The label stays put and a spinner joins it, rather than swapping in
          "Please wait…" — the button keeps its width and its meaning. */}
      {busy && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

import { useId, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'

interface FieldProps extends Omit<React.ComponentProps<'input'>, 'id'> {
  label: string
  /** Shown in red under the input and wired up via aria-describedby. */
  error?: string | null
  hint?: string
}

export function Field({ label, error, hint, className, type, ...rest }: FieldProps) {
  const id = useId()
  const [reveal, setReveal] = useState(false)
  const isPassword = type === 'password'
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined

  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-[13px] font-medium">
        {label}
      </label>

      <div className="relative">
        <input
          id={id}
          type={isPassword && reveal ? 'text' : type}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          className={cn(
            'w-full rounded-xl border bg-background/60 px-3.5 py-2.5 text-[14px]',
            'outline-none transition-colors placeholder:text-muted-foreground/60',
            'focus:border-ring/70 focus:ring-2 focus:ring-ring/20',
            isPassword && 'pr-11',
            error ? 'border-destructive/70' : 'border-border',
            className
          )}
          {...rest}
        />

        {isPassword && (
          <button
            type="button"
            onClick={() => setReveal((r) => !r)}
            aria-label={reveal ? 'Hide password' : 'Show password'}
            className="absolute right-1.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {reveal ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        )}
      </div>

      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-[12px] text-destructive">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-[12px] text-muted-foreground">
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
  ...rest
}: React.ComponentProps<'button'> & { busy?: boolean }) {
  return (
    <button
      type="submit"
      disabled={busy || rest.disabled}
      {...rest}
      className={cn(
        'w-full rounded-xl px-4 py-2.5 text-[14px] font-medium text-white transition-all',
        'bg-gradient-to-br from-indigo-500 to-purple-500',
        'hover:brightness-110 active:scale-[0.99]',
        'disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:brightness-100'
      )}
    >
      {busy ? 'Please wait…' : children}
    </button>
  )
}

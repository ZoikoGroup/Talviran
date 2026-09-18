import { useCallback, useEffect, useRef } from 'react'

interface AutoResizeProps {
  minHeight: number
  maxHeight?: number
}

/**
 * Grows a textarea with its typed content, never its placeholder.
 *
 * `adjustHeight` measures `scrollHeight`, which reflects whatever text is
 * rendered — placeholder included. Calling it unconditionally on mount (as
 * Composer's own inline version once did) meant a placeholder too long for a
 * narrow composer would wrap to two lines and the box would open already
 * tall, on an empty field nobody had touched. The fix is the same one this
 * hook already used elsewhere: mount pins the box to `minHeight` and nothing
 * more, so only `onChange` (real content) can grow it.
 */
export function useAutoResizeTextarea({ minHeight, maxHeight }: AutoResizeProps) {
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

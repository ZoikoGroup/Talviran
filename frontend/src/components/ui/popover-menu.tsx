import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/utils'

const GAP = 6
const PAD = 8
/** Below this a scrolling menu is unusable, so let it overlap instead. */
const MIN_HEIGHT = 160

interface PopoverMenuProps {
  /** The trigger's rect, captured when the menu opened. */
  anchor: DOMRect
  width: number
  /** Which edge of the menu lines up with the anchor. */
  align?: 'start' | 'end'
  /**
   * A surface the menu must not cover — normally the control the trigger sits
   * inside, such as the composer bar. Without it the menu clears only the
   * button, which leaves it overlapping the rest of that control.
   */
  clear?: DOMRect | null
  /** Side to open on when there's room for either. */
  prefer?: 'top' | 'bottom'
  onClose: () => void
  className?: string
  children: React.ReactNode
}

/**
 * A menu anchored to a trigger, portalled to `body`.
 *
 * Two things this gets right that hand-rolled positioning usually doesn't:
 *
 *  - It **measures** itself rather than estimating its height, so the decision
 *    to open below or flip above is made against the real box. Guessing is how
 *    a menu ends up hanging off the top of the screen.
 *  - It clamps into the viewport on both axes, and when it genuinely fits
 *    neither above nor below it caps its height and scrolls instead of
 *    overflowing.
 *
 * The portal matters too: composer and sidebar surfaces use `backdrop-filter`,
 * which creates a containing block — a `fixed` child inside one resolves
 * against that element instead of the viewport.
 */
export default function PopoverMenu({
  anchor,
  width,
  align = 'end',
  clear = null,
  prefer = 'bottom',
  onClose,
  className,
  children,
}: PopoverMenuProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{
    top: number
    left: number
    maxHeight?: number
  } | null>(null)

  const place = useCallback(() => {
    const el = ref.current
    if (!el) return

    const h = el.offsetHeight
    const { innerHeight: vh, innerWidth: vw } = window

    // Clear the whole control, not just the button inside it.
    const keepTop = clear ? Math.min(anchor.top, clear.top) : anchor.top
    const keepBottom = clear ? Math.max(anchor.bottom, clear.bottom) : anchor.bottom

    const roomAbove = keepTop - GAP - PAD
    const roomBelow = vh - PAD - (keepBottom + GAP)

    let openAbove =
      prefer === 'top' ? h <= roomAbove || h > roomBelow : h > roomBelow && h <= roomAbove
    // Neither side can hold it — take the roomier one and scroll.
    if (h > roomAbove && h > roomBelow) openAbove = roomAbove > roomBelow

    const room = openAbove ? roomAbove : roomBelow
    const maxHeight = h > room ? Math.max(MIN_HEIGHT, room) : undefined
    const boxH = Math.min(h, maxHeight ?? h)

    let top = openAbove ? keepTop - GAP - boxH : keepBottom + GAP
    // Clamp unconditionally. Neither candidate is inherently safe — an anchor
    // scrolled out of its own container can sit past the viewport edge, which
    // pushes even the flipped position off-screen.
    top = Math.max(PAD, Math.min(top, vh - boxH - PAD))

    const rawLeft = align === 'end' ? anchor.right - width : anchor.left
    const left = Math.max(PAD, Math.min(rawLeft, vw - width - PAD))

    setPos({ top, left, maxHeight })
  }, [anchor, width, align, clear, prefer])

  // Re-place whenever the content resizes — a menu that swaps in a delete
  // confirmation changes height after it has already been positioned.
  useLayoutEffect(() => {
    place()
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(place)
    ro.observe(el)
    return () => ro.disconnect()
  }, [place])

  useEffect(() => {
    // Whatever had focus when the menu opened — the trigger, for a click or
    // a keyboard activation.
    const trigger = document.activeElement as HTMLElement | null
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      // Escape should hand focus back rather than dropping it on the body.
      trigger?.focus?.()
      onClose()
    }
    // Capture, so a scroll in any nested scroller dismisses it too.
    window.addEventListener('scroll', onClose, true)
    window.addEventListener('resize', onClose)
    document.addEventListener('mousedown', onClose)
    document.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('scroll', onClose, true)
      window.removeEventListener('resize', onClose)
      document.removeEventListener('mousedown', onClose)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  return createPortal(
    <div
      ref={ref}
      role="menu"
      onMouseDown={(e) => e.stopPropagation()}
      style={{
        left: pos?.left ?? 0,
        top: pos?.top ?? 0,
        width,
        maxHeight: pos?.maxHeight,
        overflowY: pos?.maxHeight ? 'auto' : undefined,
        // Hidden (not unmounted) for the first frame so it can be measured
        // at full size without flashing in the wrong place.
        visibility: pos ? 'visible' : 'hidden',
      }}
      className={cn(
        'scrollbar-slim fixed z-50 rounded-xl border p-1.5 shadow-2xl shadow-black/40',
        className
      )}
    >
      {children}
    </div>,
    document.body
  )
}

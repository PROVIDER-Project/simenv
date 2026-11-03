import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

/** Keep selection changes from shrinking the scroll range under the reader. */
export default function StableInspector({ children }: { children: ReactNode }) {
  const content = useRef<HTMLDivElement | null>(null)
  const [retained, setRetained] = useState({ width: 0, height: 0 })
  useLayoutEffect(() => {
    const element = content.current
    if (!element) return
    const measure = () => {
      const box = element.getBoundingClientRect()
      if (box.width <= 0) return // Collapsed panels must not lose their reservation.
      const width = Math.round(box.width * 100) / 100
      const naturalHeight = Math.ceil(box.height)
      setRetained(previous => {
        const height = width === previous.width ? Math.max(previous.height, naturalHeight) : naturalHeight
        return width === previous.width && height === previous.height ? previous : { width, height }
      })
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return <div className="sim-stable-inspector" style={{ minHeight: retained.height }}>
    <div className="sim-stable-inspector-content" ref={content}>{children}</div>
  </div>
}

/**
 * Shared skeleton building blocks (styles in overhaul.css .skeleton).
 * Compose these instead of ad-hoc spinners while data loads.
 */
export function SkeletonText({ lines = 2 }: { lines?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton skeleton--text" style={{ width: `${88 - i * 18}%` }} />
      ))}
    </div>
  )
}

export function SkeletonNumber() {
  return <div className="skeleton skeleton--num" aria-hidden />
}

export function SkeletonBlock({ height }: { height?: number }) {
  return (
    <div
      className="skeleton skeleton--block"
      style={height ? { height } : undefined}
      aria-hidden
    />
  )
}

export function SkeletonPanelRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-3" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <SkeletonNumber />
          <div className="flex-1">
            <SkeletonText lines={1} />
          </div>
        </div>
      ))}
    </div>
  )
}

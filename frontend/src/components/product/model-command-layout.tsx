import { useCallback, useState, type ReactNode } from "react"

import { useIsNarrowViewport } from "@/hooks/use-media-query"
import { cn } from "@/lib/utils"

export type ModelCommandSectionConfig = {
  id: string
  label: string
  badge?: number | string
  content: ReactNode
  /** Hide from mobile section nav (always shown on desktop stack). */
  desktopOnly?: boolean
}

export const ModelCommandLayout = ({
  sections,
  defaultMobileSectionId = "picks",
  className,
}: {
  sections: ModelCommandSectionConfig[]
  defaultMobileSectionId?: string
  className?: string
}) => {
  const isNarrow = useIsNarrowViewport()
  const mobileSections = sections.filter((section) => !section.desktopOnly)
  const [activeId, setActiveId] = useState(defaultMobileSectionId)

  const handleSectionClick = useCallback((id: string) => {
    setActiveId(id)
    const el = document.getElementById(`model-section-anchor-${id}`)
    el?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [])

  if (!isNarrow) {
    return (
      <div className={cn("model-command-layout flex flex-col gap-5", className)} data-testid="model-command-layout">
        {sections.map((section) => (
          <div key={section.id} id={`model-section-anchor-${section.id}`}>
            {section.content}
          </div>
        ))}
      </div>
    )
  }

  const activeSection =
    mobileSections.find((section) => section.id === activeId) ?? mobileSections[0]

  return (
    <div className={cn("model-command-center", className)} data-testid="model-command-layout-mobile">
      <nav className="model-section-nav" aria-label="Workspace sections">
        {mobileSections.map((section) => (
          <button
            key={section.id}
            type="button"
            className={cn(
              "model-section-nav__item",
              activeSection?.id === section.id && "model-section-nav__item--active",
            )}
            onClick={() => handleSectionClick(section.id)}
            data-testid={
              section.id === "rankings"
                ? "cockpit-tab-rankings"
                : `model-section-nav-${section.id}`
            }
            aria-current={activeSection?.id === section.id ? "true" : undefined}
          >
            {section.label}
            {section.badge != null ? (
              <span className="model-section-nav__badge">{section.badge}</span>
            ) : null}
          </button>
        ))}
      </nav>
      <div id={`model-section-anchor-${activeSection?.id}`}>{activeSection?.content}</div>
    </div>
  )
}

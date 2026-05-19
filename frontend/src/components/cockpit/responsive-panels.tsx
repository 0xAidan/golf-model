import { useState, type ReactNode } from "react"
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels"

import { useViewportTier } from "@/hooks/use-viewport"
import { cn } from "@/lib/utils"

export type CockpitTabOption = {
  id: string
  label: string
  content: ReactNode
  badge?: string | number
}

export function CockpitSegmentTabs({
  tabs,
  value,
  onChange,
  ariaLabel,
  className,
}: {
  tabs: CockpitTabOption[]
  value: string
  onChange: (id: string) => void
  ariaLabel: string
  className?: string
}) {
  return (
    <div className={cn("cockpit-segment-tabs", className)} role="tablist" aria-label={ariaLabel}>
      {tabs.map((tab, idx) => {
        const active = tab.id === value
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`${tab.id}-tab`}
            aria-selected={active}
            aria-controls={`${tab.id}-panel`}
            aria-posinset={idx + 1}
            aria-setsize={tabs.length}
            className={cn("cockpit-segment-tab", active && "active")}
            onClick={() => onChange(tab.id)}
            data-testid={`cockpit-tab-${tab.id}`}
          >
            <span>{tab.label}</span>
            {tab.badge != null && tab.badge !== "" ? (
              <span className="cockpit-segment-tab-badge" aria-hidden="true">
                {tab.badge}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

function CockpitTabPanels({ tabs, activeId }: { tabs: CockpitTabOption[]; activeId: string }) {
  return (
    <>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          id={`${tab.id}-panel`}
          role="tabpanel"
          aria-labelledby={`${tab.id}-tab`}
          hidden={tab.id !== activeId}
          className="cockpit-tab-panel"
          data-testid={`cockpit-panel-${tab.id}`}
        >
          {tab.id === activeId ? tab.content : null}
        </div>
      ))}
    </>
  )
}

function firstTabId(tabs: CockpitTabOption[]): string {
  return tabs[0]?.id ?? ""
}

export function CockpitVerticalSections({
  autoSaveId,
  sections,
  defaultActiveId,
  stackClassName,
}: {
  autoSaveId: string
  sections: CockpitTabOption[]
  defaultActiveId?: string
  stackClassName?: string
}) {
  const tier = useViewportTier()
  const [activeId, setActiveId] = useState(defaultActiveId ?? firstTabId(sections))

  if (tier === "mobile" || tier === "tablet") {
    const active = sections.some((s) => s.id === activeId) ? activeId : firstTabId(sections)
    return (
      <div className={cn("cockpit-mobile-section-stack", stackClassName)}>
        <CockpitSegmentTabs
          tabs={sections}
          value={active}
          onChange={setActiveId}
          ariaLabel="Section"
        />
        <CockpitTabPanels tabs={sections} activeId={active} />
      </div>
    )
  }

  const sizes = sections.length === 3 ? [42, 38, 20] : sections.map(() => 100 / sections.length)
  return (
    <PanelGroup
      direction="vertical"
      autoSaveId={autoSaveId}
      className="cockpit-vertical-panels cockpit-left-rail-panels"
    >
      {sections.map((section, index) => (
        <FragmentSection
          key={section.id}
          section={section}
          defaultSize={sizes[index] ?? 33}
          minSize={index === sections.length - 1 ? 12 : 14}
          showHandle={index < sections.length - 1}
          handleLabel={`Resize ${section.label}`}
        />
      ))}
    </PanelGroup>
  )
}

function FragmentSection({
  section,
  defaultSize,
  minSize,
  showHandle,
  handleLabel,
}: {
  section: CockpitTabOption
  defaultSize: number
  minSize: number
  showHandle: boolean
  handleLabel: string
}) {
  return (
    <>
      <Panel defaultSize={defaultSize} minSize={minSize} className="cockpit-panel-shell">
        <div className="cockpit-panel-fill cockpit-left-rail-section" style={{ gap: 4 }}>
          {section.content}
        </div>
      </Panel>
      {showHandle ? (
        <PanelResizeHandle
          className="cockpit-resize-handle cockpit-resize-handle-row"
          aria-label={handleLabel}
        />
      ) : null}
    </>
  )
}

export function CockpitTabbedStack({
  tabs,
  defaultTabId,
  ariaLabel,
  className,
}: {
  tabs: CockpitTabOption[]
  defaultTabId?: string
  ariaLabel: string
  className?: string
}) {
  const [activeId, setActiveId] = useState(defaultTabId ?? firstTabId(tabs))
  const active = tabs.some((t) => t.id === activeId) ? activeId : firstTabId(tabs)

  return (
    <div className={cn("cockpit-tabbed-stack", className)}>
      <CockpitSegmentTabs tabs={tabs} value={active} onChange={setActiveId} ariaLabel={ariaLabel} />
      <CockpitTabPanels tabs={tabs} activeId={active} />
    </div>
  )
}

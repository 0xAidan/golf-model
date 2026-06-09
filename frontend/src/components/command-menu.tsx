import { Command } from "cmdk"
import { useCallback, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { Moon, RefreshCw, Star, Sun, Monitor } from "lucide-react"

import { useTheme } from "@/components/theme-provider"
import { cn } from "@/lib/utils"

const NAV_ITEMS = [
  { id: "prediction", label: "Dashboard", path: "/" },
  { id: "lab-board", label: "Lab", path: "/lab" },
  { id: "players", label: "Players", path: "/players" },
  { id: "grading", label: "Results", path: "/results" },
  { id: "diagnostics", label: "System", path: "/system" },
  { id: "matchups", label: "Picks (legacy)", path: "/matchups" },
  { id: "lab-picks", label: "Lab picks (legacy)", path: "/lab/picks" },
  { id: "track-record", label: "Track record (legacy)", path: "/track-record" },
  { id: "legacy-model", label: "Legacy model", path: "/research/legacy-model" },
  { id: "champion-challenger", label: "Champ / challenger", path: "/research/champion-challenger" },
  { id: "diagnostics-legacy", label: "Diagnostics (legacy)", path: "/research/diagnostics" },
] as const

export function CommandMenu({
  open,
  onOpenChange,
  onGrade,
  onRefresh,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onGrade?: () => void
  onRefresh?: () => void
}) {
  const navigate = useNavigate()
  const { setTheme } = useTheme()

  const handleSelect = useCallback(
    (value: string) => {
      const nav = NAV_ITEMS.find((item) => item.id === value)
      if (nav) {
        navigate(nav.path)
        onOpenChange(false)
        return
      }
      if (value === "action-grade") {
        onGrade?.()
        onOpenChange(false)
        return
      }
      if (value === "action-refresh") {
        onRefresh?.()
        onOpenChange(false)
        return
      }
      if (value.startsWith("theme-")) {
        const theme = value.replace("theme-", "") as "light" | "dark" | "system"
        setTheme(theme)
        onOpenChange(false)
      }
    },
    [navigate, onGrade, onOpenChange, onRefresh, setTheme],
  )

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        onOpenChange(!open)
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [open, onOpenChange])

  if (!open) return null

  return (
    <div
      className="command-menu-overlay"
      role="presentation"
      onClick={() => onOpenChange(false)}
      onKeyDown={(e) => e.key === "Escape" && onOpenChange(false)}
    >
      <Command
        className="command-menu"
        data-testid="command-menu"
        onClick={(e) => e.stopPropagation()}
      >
        <Command.Input placeholder="Jump to route or run action…" aria-label="Command menu" />
        <Command.List>
          <Command.Empty>No results.</Command.Empty>
          <Command.Group heading="Navigate">
            {NAV_ITEMS.map((item) => (
              <Command.Item key={item.id} value={item.id} onSelect={handleSelect}>
                {item.label}
              </Command.Item>
            ))}
          </Command.Group>
          <Command.Group heading="Actions">
            <Command.Item value="action-grade" onSelect={handleSelect}>
              <Star size={14} aria-hidden />
              Grade event
            </Command.Item>
            <Command.Item value="action-refresh" onSelect={handleSelect}>
              <RefreshCw size={14} aria-hidden />
              Refresh snapshot
            </Command.Item>
          </Command.Group>
          <Command.Group heading="Theme">
            <Command.Item value="theme-light" onSelect={handleSelect}>
              <Sun size={14} aria-hidden />
              Light
            </Command.Item>
            <Command.Item value="theme-dark" onSelect={handleSelect}>
              <Moon size={14} aria-hidden />
              Dark
            </Command.Item>
            <Command.Item value="theme-system" onSelect={handleSelect}>
              <Monitor size={14} aria-hidden />
              System
            </Command.Item>
          </Command.Group>
        </Command.List>
      </Command>
    </div>
  )
}

export function CommandMenuTrigger({
  onClick,
  className,
}: {
  onClick: () => void
  className?: string
}) {
  return (
    <button
      type="button"
      className={cn("command-menu-trigger", className)}
      onClick={onClick}
      aria-label="Open command menu"
      title="Command menu (⌘K)"
    >
      ⌘K
    </button>
  )
}

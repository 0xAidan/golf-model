import { Waves } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useCalmMode } from "@/providers/calm-mode-provider"

export function CalmModeToggle() {
  const { calm, setCalm } = useCalmMode()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Motion: ${calm ? "calm" : "full"}. Open menu`}
          data-testid="calm-mode-toggle"
          className={calm ? "text-[var(--accent-focus)]" : undefined}
        >
          <Waves size={15} aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[11rem]">
        <DropdownMenuItem
          onClick={() => setCalm(false)}
          data-testid="calm-option-full"
          className={!calm ? "bg-muted" : undefined}
        >
          Full motion
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => setCalm(true)}
          data-testid="calm-option-calm"
          className={calm ? "bg-muted" : undefined}
        >
          Calm (scan mode)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

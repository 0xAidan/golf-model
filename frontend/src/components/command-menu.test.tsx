import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { CommandMenu } from "@/components/command-menu"
import { ThemeProvider } from "@/components/theme-provider"

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}))

describe("CommandMenu", () => {
  it("renders when open", () => {
    render(
      <ThemeProvider>
        <CommandMenu open onOpenChange={vi.fn()} />
      </ThemeProvider>,
    )
    expect(screen.getByRole("combobox")).toBeInTheDocument()
  })
})

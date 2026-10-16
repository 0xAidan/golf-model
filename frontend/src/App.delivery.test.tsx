import { cleanup, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Link, MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import App from "@/App"

const { loadNotifications } = vi.hoisted(() => ({ loadNotifications: vi.fn() }))

vi.mock("@/features/learning-workspace/learning-workspace", () => ({
  LearningWorkspace: () => <main><h1>Rankings workspace</h1><Link to="/system">Open research tools</Link></main>,
}))
vi.mock("@/app/legacy-app", () => ({
  default: () => <main><h1>Research tools</h1><Link to="/">Return to rankings</Link></main>,
}))
vi.mock("sonner", () => {
  loadNotifications()
  return { Toaster: () => <div role="status">Legacy notifications available</div> }
})

afterEach(cleanup)

describe("route delivery", () => {
  it("defers legacy notifications until needed and retains them on return to rankings", async () => {
    const user = userEvent.setup()
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>)

    expect(await screen.findByRole("heading", { name: "Rankings workspace" })).toBeInTheDocument()
    expect(loadNotifications).not.toHaveBeenCalled()
    expect(screen.queryByText("Legacy notifications available")).not.toBeInTheDocument()

    await user.click(screen.getByRole("link", { name: "Open research tools" }))
    expect(await screen.findByRole("heading", { name: "Research tools" })).toBeInTheDocument()
    const notificationHost = await screen.findByText("Legacy notifications available")
    expect(loadNotifications).toHaveBeenCalledOnce()

    await user.click(screen.getByRole("link", { name: "Return to rankings" }))
    expect(await screen.findByRole("heading", { name: "Rankings workspace" })).toBeInTheDocument()
    expect(screen.getByText("Legacy notifications available")).toBe(notificationHost)
  })
})

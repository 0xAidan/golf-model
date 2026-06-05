import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { MemoryRouter } from "react-router-dom"

import { ThemeProvider } from "@/components/theme-provider"
import { InteractionProvider } from "@/providers/interaction-provider"

export function wrapMonitoringTest(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <InteractionProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </InteractionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  )
}

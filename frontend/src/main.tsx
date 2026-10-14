import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter } from "react-router-dom"

import App from "@/App"
import { ChartThemeProvider } from "@/components/chart-theme-provider"
import { ThemeProvider } from "@/components/theme-provider"
import { prepareErrorReporting } from "@/observability/sentry-startup"
import "@/index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

const legacyHashPath = window.location.hash
if (legacyHashPath.startsWith("#/")) {
  window.history.replaceState(null, "", legacyHashPath.slice(1))
}

function renderApplication() {
  createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <ChartThemeProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </ChartThemeProvider>
    </ThemeProvider>
  </StrictMode>,
  )
}

// Configured reporting is ready before React renders; unconfigured deployments skip the SDK.
void prepareErrorReporting().then(renderApplication)

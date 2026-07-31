import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter } from "react-router-dom"

import App from "@/App"
import { ChartThemeProvider } from "@/components/chart-theme-provider"
import { ThemeProvider } from "@/components/theme-provider"
import { initSentry } from "@/observability/sentry"
import { Toaster } from "sonner"
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

initSentry()

const legacyHashPath = window.location.hash
if (legacyHashPath.startsWith("#/")) {
  window.history.replaceState(null, "", legacyHashPath.slice(1))
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <ChartThemeProvider>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
            <Toaster position="top-center" richColors closeButton />
          </BrowserRouter>
        </QueryClientProvider>
      </ChartThemeProvider>
    </ThemeProvider>
  </StrictMode>,
)

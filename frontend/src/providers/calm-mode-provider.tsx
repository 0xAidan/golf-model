import { createContext, useContext, useEffect, useState, type ReactNode } from "react"

type CalmModeContextValue = {
  calm: boolean
  setCalm: (value: boolean) => void
  toggleCalm: () => void
}

const CalmModeContext = createContext<CalmModeContextValue | null>(null)

const STORAGE_KEY = "golf-model.calm-mode"

function readInitial(): boolean {
  if (typeof window === "undefined") return false
  return window.localStorage.getItem(STORAGE_KEY) === "true"
}

export function CalmModeProvider({ children }: { children: ReactNode }) {
  const [calm, setCalmState] = useState<boolean>(readInitial)

  useEffect(() => {
    document.documentElement.dataset.calm = calm ? "true" : "false"
    window.localStorage.setItem(STORAGE_KEY, calm ? "true" : "false")
  }, [calm])

  const value: CalmModeContextValue = {
    calm,
    setCalm: setCalmState,
    toggleCalm: () => setCalmState((prev) => !prev),
  }

  return <CalmModeContext.Provider value={value}>{children}</CalmModeContext.Provider>
}

export function useCalmMode(): CalmModeContextValue {
  const ctx = useContext(CalmModeContext)
  if (!ctx) {
    // Safe default outside a provider (tests, isolated mounts).
    return { calm: false, setCalm: () => {}, toggleCalm: () => {} }
  }
  return ctx
}

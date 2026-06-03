import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import {
  applyThemeClass,
  persistTheme,
  readStoredTheme,
  type ThemeSetting,
} from "@/lib/theme"

type ThemeContextValue = {
  theme: ThemeSetting
  setTheme: (next: ThemeSetting) => void
  resolvedDark: boolean
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeSetting>(() => readStoredTheme())
  const [resolvedDark, setResolvedDark] = useState(() =>
    typeof document !== "undefined"
      ? document.documentElement.classList.contains("dark")
      : true,
  )

  const setTheme = useCallback((next: ThemeSetting) => {
    persistTheme(next)
    setThemeState(next)
    setResolvedDark(document.documentElement.classList.contains("dark"))
  }, [])

  useEffect(() => {
    applyThemeClass(theme)
    setResolvedDark(document.documentElement.classList.contains("dark"))

    if (theme !== "system") return

    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      applyThemeClass("system")
      setResolvedDark(mq.matches)
    }
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [theme])

  const value = useMemo(
    () => ({ theme, setTheme, resolvedDark }),
    [theme, setTheme, resolvedDark],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider")
  return ctx
}

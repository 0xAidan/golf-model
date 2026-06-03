export type ThemeSetting = "light" | "dark" | "system"

export const THEME_STORAGE_KEY = "golf-model.theme"

export function resolveThemeClass(setting: ThemeSetting): boolean {
  if (setting === "dark") return true
  if (setting === "light") return false
  if (typeof window === "undefined") return true
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

export function applyThemeClass(setting: ThemeSetting): void {
  if (typeof document === "undefined") return
  document.documentElement.classList.toggle("dark", resolveThemeClass(setting))
  document.documentElement.style.colorScheme = resolveThemeClass(setting) ? "dark" : "light"
}

export function readStoredTheme(): ThemeSetting {
  if (typeof localStorage === "undefined") return "system"
  const raw = localStorage.getItem(THEME_STORAGE_KEY)
  if (raw === "light" || raw === "dark" || raw === "system") return raw
  return "system"
}

export function persistTheme(setting: ThemeSetting): void {
  localStorage.setItem(THEME_STORAGE_KEY, setting)
  applyThemeClass(setting)
}

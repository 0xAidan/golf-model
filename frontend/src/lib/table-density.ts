import { useSyncExternalStore } from "react"

export type TableDensityPreference = "compact" | "comfortable"

const STORAGE_KEY = "golf-model.table-density"

function readDensity(): TableDensityPreference {
  if (typeof window === "undefined") return "compact"
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === "comfortable" ? "comfortable" : "compact"
}

function subscribe(callback: () => void) {
  if (typeof window === "undefined") return () => {}
  const handler = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY) callback()
  }
  window.addEventListener("storage", handler)
  window.addEventListener("table-density-change", callback)
  return () => {
    window.removeEventListener("storage", handler)
    window.removeEventListener("table-density-change", callback)
  }
}

export function setTableDensity(density: TableDensityPreference) {
  window.localStorage.setItem(STORAGE_KEY, density)
  window.dispatchEvent(new Event("table-density-change"))
}

export function useTableDensity(): TableDensityPreference {
  return useSyncExternalStore(subscribe, readDensity, () => "compact" as const)
}

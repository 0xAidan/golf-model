import { useState } from "react"

export type PredictionTab = "live" | "upcoming" | "past"

export function getDefaultPredictionTab(isLiveActive: boolean): PredictionTab {
  return isLiveActive ? "live" : "upcoming"
}

export function shouldAdoptLiveMode({
  currentTab,
  isLiveActive,
  hasUserSelected,
  hasAutoSynced,
}: {
  currentTab: PredictionTab
  isLiveActive: boolean
  hasUserSelected: boolean
  hasAutoSynced: boolean
}) {
  return isLiveActive && currentTab === "upcoming" && !hasUserSelected && !hasAutoSynced
}

export function usePredictionTab(isLiveActive: boolean) {
  const [storedPredictionTab, setStoredPredictionTab] = useState<PredictionTab>(() => getDefaultPredictionTab(isLiveActive))
  const [hasUserSelected, setHasUserSelected] = useState(false)
  const predictionTab = shouldAdoptLiveMode({
    currentTab: storedPredictionTab,
    isLiveActive,
    hasUserSelected,
    hasAutoSynced: false,
  })
    ? "live"
    : storedPredictionTab

  const handlePredictionTabChange = (nextTab: PredictionTab) => {
    setHasUserSelected(true)
    setStoredPredictionTab(nextTab)
  }

  return {
    predictionTab,
    setPredictionTab: handlePredictionTabChange,
  }
}

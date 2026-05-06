/** localStorage so power users can keep the lab research deck open across visits */
export const LAB_RESEARCH_INSTRUMENTATION_EXPANDED_KEY =
  "golf-model:cockpit-lab-research-instrumentation-expanded"

export function readLabResearchInstrumentationExpanded(): boolean {
  if (typeof window === "undefined") {
    return false
  }
  try {
    const v = window.localStorage.getItem(LAB_RESEARCH_INSTRUMENTATION_EXPANDED_KEY)
    if (v === "1" || v === "true") {
      return true
    }
    if (v === "0" || v === "false") {
      return false
    }
  } catch {
    /* quota / private mode */
  }
  return false
}

export function persistLabResearchInstrumentationExpanded(open: boolean): void {
  try {
    window.localStorage.setItem(LAB_RESEARCH_INSTRUMENTATION_EXPANDED_KEY, open ? "1" : "0")
  } catch {
    /* ignore */
  }
}

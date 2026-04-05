export function formatPercent(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  return `${(value * 100).toFixed(digits)}%`
}

export function formatNumber(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  return value.toFixed(digits)
}

export function formatUnits(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "--"
  }
  const sign = value > 0 ? "+" : ""
  return `${sign}${value.toFixed(2)}u`
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "--"
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

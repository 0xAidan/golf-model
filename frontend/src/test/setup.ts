import "@testing-library/jest-dom/vitest"

const localStorageBacking = new Map<string, string>()

const localStorageMock: Storage = {
  get length() {
    return localStorageBacking.size
  },
  clear() {
    localStorageBacking.clear()
  },
  getItem(key: string) {
    return localStorageBacking.get(key) ?? null
  },
  key(index: number) {
    return [...localStorageBacking.keys()][index] ?? null
  },
  removeItem(key: string) {
    localStorageBacking.delete(key)
  },
  setItem(key: string, value: string) {
    localStorageBacking.set(key, String(value))
  },
}

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  writable: true,
  configurable: true,
})

Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: (query: string) => ({
    matches: query.includes("min-width: 1200px"),
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false
    },
  }),
})

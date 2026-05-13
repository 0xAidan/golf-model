import "@testing-library/jest-dom/vitest"

Object.defineProperty(window, "matchMedia", {
  writable: true,
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener(_type: string, _listener: EventListener) {},
    removeEventListener() {},
    dispatchEvent() {
      return false
    },
  }),
})

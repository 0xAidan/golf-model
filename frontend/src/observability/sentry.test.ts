import { describe, expect, it } from "vitest"

import { scrubSentryBreadcrumb, scrubSentryEvent } from "@/observability/sentry"

describe("scrubSentryEvent", () => {
  it("removes credentials, request bodies, and sensitive query values", () => {
    const event = scrubSentryEvent({
      type: undefined,
      request: {
        headers: {
          Authorization: "Bearer secret",
          "X-Api-Key": "api-secret",
          "X-Request-ID": "safe",
        },
        data: { password: "secret" },
        url: "https://example.test/api?token=secret&mode=live",
      },
    })

    expect(event.request?.headers).toEqual({ "X-Request-ID": "safe" })
    expect(event.request?.data).toBe("[Filtered]")
    expect(event.request?.url).toBe("https://example.test/api?token=%5BFiltered%5D&mode=live")
  })

  it("removes shared-card fragments from requests, navigation and console breadcrumbs", () => {
    const payload = "private-saved-quote-payload"
    const url = `https://example.test/shared-card#card=${payload}`
    const event = scrubSentryEvent({
      type: undefined,
      request: { url },
      breadcrumbs: [
        { category: "navigation", data: { from: url, to: `https://example.test/card#card=${payload}` } },
        { category: "console", message: `Could not open ${url}`, data: { arguments: [url] } },
      ],
      tags: { route: `/shared-card#card=${payload}` },
    })
    expect(event.request.url).toBe("https://example.test/shared-card")
    expect(event.breadcrumbs[0].data).toEqual({ from: "https://example.test/shared-card", to: "https://example.test/card" })
    expect(JSON.stringify(event)).not.toContain(payload)
  })

  it("scrubs breadcrumb payloads immediately, even without an event request", () => {
    const breadcrumb = scrubSentryBreadcrumb({
      category: "navigation",
      data: { from: "https://example.test/card#card=private-old", to: "https://example.test/shared-card?token=secret#card=private-new" },
    })
    expect(breadcrumb.data).toEqual({
      from: "https://example.test/card",
      to: "https://example.test/shared-card?token=%5BFiltered%5D",
    })
    const event = scrubSentryEvent({
      type: undefined,
      breadcrumbs: [breadcrumb],
      extra: { sourceUrl: "https://example.test/shared-card#card=private-extra" },
    })
    expect(JSON.stringify(event)).not.toMatch(/private-|secret/)
  })

  it("scrubs transaction spans as well as error events without mutating the source", () => {
    const source = {
      type: "transaction" as const,
      transaction: "/shared-card#card=private-title",
      spans: [{ span_id: "1", trace_id: "2", start_timestamp: 1, timestamp: 2,
        data: { "url.full": "https://example.test/shared-card#card=private-span" } }],
    }
    const event = scrubSentryEvent(source)
    expect(JSON.stringify(event)).not.toContain("private-")
    expect(source.transaction).toContain("private-title")
    expect(source.spans[0].data["url.full"]).toContain("private-span")
  })
})

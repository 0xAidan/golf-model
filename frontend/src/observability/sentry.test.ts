import { describe, expect, it } from "vitest"

import { scrubSentryEvent } from "@/observability/sentry"

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
})

import { afterEach, describe, expect, it, vi } from "vitest"

import { api } from "@/lib/api"

describe("api player profile paths", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("encodes player keys for profile endpoints", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({ ok: true, json: async () => ({ player_key: "ok" }) } as Response)

    await api.getPlayerProfile("Rory McIlroy/1", 123, 7)
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      "/api/players/Rory%20McIlroy%2F1/profile?tournament_id=123&course_num=7",
    )

    await api.getPlayerStandaloneProfile("Caméron Young")
    expect(String(fetchMock.mock.calls[1]?.[0])).toBe(
      "/api/players/Cam%C3%A9ron%20Young/standalone-profile",
    )
  })
})

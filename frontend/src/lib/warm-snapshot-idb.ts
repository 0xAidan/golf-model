import type { LiveRefreshSnapshotResponse } from "@/lib/types"

const DB_NAME = "golf-model-cache"
const DB_VERSION = 1
const STORE = "snapshots"
const KEY = "warm-envelope"
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000
const DEFAULT_STALE_AFTER_SECONDS = 3900

const envelopeIsTooStale = (envelope: LiveRefreshSnapshotResponse): boolean => {
  if (
    envelope.age_seconds != null &&
    envelope.stale_after_seconds != null &&
    envelope.age_seconds > envelope.stale_after_seconds
  ) {
    return true
  }
  if (envelope.age_seconds != null && envelope.age_seconds > DEFAULT_STALE_AFTER_SECONDS) {
    return true
  }
  const generatedAt = envelope.generated_at ?? envelope.snapshot?.generated_at
  if (!generatedAt) return false
  try {
    const generatedMs = Date.parse(generatedAt)
    if (!Number.isFinite(generatedMs)) return false
    return Date.now() - generatedMs > DEFAULT_STALE_AFTER_SECONDS * 1000
  } catch {
    return false
  }
}

type StoredEnvelope = {
  savedAt: number
  envelope: LiveRefreshSnapshotResponse
}

const openDb = (): Promise<IDBDatabase> =>
  new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("indexedDB unavailable"))
      return
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onerror = () => reject(req.error ?? new Error("idb open failed"))
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE)
      }
    }
    req.onsuccess = () => resolve(req.result)
  })

export const readIdbWarmSnapshotEnvelope = async (): Promise<LiveRefreshSnapshotResponse | null> => {
  try {
    const db = await openDb()
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, "readonly")
      const store = tx.objectStore(STORE)
      const getReq = store.get(KEY)
      getReq.onerror = () => reject(getReq.error ?? new Error("idb get failed"))
      getReq.onsuccess = () => {
        const row = getReq.result as StoredEnvelope | undefined
        if (!row?.envelope?.snapshot) {
          resolve(null)
          return
        }
        if (Date.now() - row.savedAt > MAX_AGE_MS) {
          resolve(null)
          return
        }
        if (envelopeIsTooStale(row.envelope)) {
          resolve(null)
          return
        }
        resolve(row.envelope)
      }
    })
  } catch {
    return null
  }
}

export const writeIdbWarmSnapshotEnvelope = async (envelope: LiveRefreshSnapshotResponse): Promise<void> => {
  if (!envelope.snapshot) return
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite")
      const store = tx.objectStore(STORE)
      const putReq = store.put({ savedAt: Date.now(), envelope } satisfies StoredEnvelope, KEY)
      putReq.onerror = () => reject(putReq.error ?? new Error("idb put failed"))
      putReq.onsuccess = () => resolve()
    })
  } catch {
    // Best-effort cache
  }
}

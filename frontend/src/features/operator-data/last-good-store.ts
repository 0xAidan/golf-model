import type { OperatorBoard, OperatorMode, OperatorTrack } from "@/features/operator-data/operator-api"

const DB_NAME = "golf-model-operator-cache"
const DB_VERSION = 1
const STORE_NAME = "last-good-boards"
const DEFAULT_MAX_ENTRIES = 12

export type BoardIdentity = {
  schemaVersion: string
  release: string
  track: OperatorTrack
  mode: OperatorMode
  eventId: string
}

export type CachedOperatorBoard = {
  identity: BoardIdentity
  board: OperatorBoard
  savedAt: number
  snapshotId: string | null
}

type LastGoodBoardStore = {
  read: (identity: BoardIdentity) => Promise<CachedOperatorBoard | null>
  save: (entry: CachedOperatorBoard) => Promise<void>
}

type StoreOptions = {
  maxEntries?: number
  release: string
}

const identityKey = (identity: BoardIdentity): string =>
  [identity.schemaVersion, identity.release, identity.track, identity.mode, identity.eventId].join("|")

const matchingIdentity = (entry: CachedOperatorBoard): boolean =>
  entry.board.schema_version === entry.identity.schemaVersion &&
  entry.board.track === entry.identity.track &&
  entry.board.mode === entry.identity.mode &&
  entry.board.event.event_id === entry.identity.eventId &&
  entry.identity.eventId.length > 0

const createMemoryStore = (maxEntries: number): LastGoodBoardStore => {
  const entries = new Map<string, CachedOperatorBoard>()
  return {
    async read(identity) {
      const entry = entries.get(identityKey(identity))
      return entry && matchingIdentity(entry) ? entry : null
    },
    async save(entry) {
      if (!matchingIdentity(entry)) return
      entries.set(identityKey(entry.identity), entry)
      const excess = [...entries.entries()]
        .sort(([, left], [, right]) => right.savedAt - left.savedAt)
        .slice(maxEntries)
      excess.forEach(([key]) => entries.delete(key))
    },
  }
}

const openDatabase = (): Promise<IDBDatabase> =>
  new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onerror = () => reject(request.error ?? new Error("Unable to open operator cache"))
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME, { keyPath: "key" })
      }
    }
    request.onsuccess = () => resolve(request.result)
  })

type StoredOperatorBoard = CachedOperatorBoard & { key: string }

const asStored = (entry: CachedOperatorBoard): StoredOperatorBoard => ({ ...entry, key: identityKey(entry.identity) })

const createIndexedDbStore = (maxEntries: number): LastGoodBoardStore => ({
  async read(identity) {
    const database = await openDatabase()
    return new Promise<CachedOperatorBoard | null>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readonly")
      const request = transaction.objectStore(STORE_NAME).get(identityKey(identity))
      request.onerror = () => reject(request.error ?? new Error("Unable to read operator cache"))
      request.onsuccess = () => {
        const entry = request.result as StoredOperatorBoard | undefined
        resolve(entry && matchingIdentity(entry) ? entry : null)
      }
    })
  },
  async save(entry) {
    if (!matchingIdentity(entry)) return
    const database = await openDatabase()
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite")
      const store = transaction.objectStore(STORE_NAME)
      const write = store.put(asStored(entry))
      write.onerror = () => reject(write.error ?? new Error("Unable to save operator cache"))
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error("Unable to save operator cache"))
    })

    const databaseForPrune = await openDatabase()
    await new Promise<void>((resolve, reject) => {
      const transaction = databaseForPrune.transaction(STORE_NAME, "readwrite")
      const store = transaction.objectStore(STORE_NAME)
      const all = store.getAll()
      all.onerror = () => reject(all.error ?? new Error("Unable to prune operator cache"))
      all.onsuccess = () => {
        const expired = (all.result as StoredOperatorBoard[])
          .sort((left, right) => right.savedAt - left.savedAt)
          .slice(maxEntries)
        expired.forEach((item) => store.delete(item.key))
      }
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error("Unable to prune operator cache"))
    })
  },
})

export const createLastGoodBoardStore = ({
  maxEntries = DEFAULT_MAX_ENTRIES,
  release,
}: StoreOptions): LastGoodBoardStore => {
  const normalizedMaxEntries = Math.max(1, maxEntries)
  if (typeof indexedDB === "undefined") return createMemoryStore(normalizedMaxEntries)

  const persistentStore = createIndexedDbStore(normalizedMaxEntries)
  const memoryStore = createMemoryStore(normalizedMaxEntries)
  return {
    async read(identity) {
      if (identity.release !== release) return null
      try {
        return await persistentStore.read(identity)
      } catch {
        return memoryStore.read(identity)
      }
    },
    async save(entry) {
      if (entry.identity.release !== release || !matchingIdentity(entry)) return
      await memoryStore.save(entry)
      try {
        await persistentStore.save(entry)
      } catch {
        // Cache persistence is best-effort; memory remains available for this session.
      }
    },
  }
}

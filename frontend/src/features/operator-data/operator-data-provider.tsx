import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { keepPreviousData, useQuery } from "@tanstack/react-query"

import {
  getOperatorBoard,
  getOperatorBootstrap,
  type ApiError,
  type OperatorBoard,
  type OperatorBootstrap,
  type OperatorMode,
  type OperatorTrack,
} from "@/features/operator-data/operator-api"
import {
  createLastGoodBoardStore,
  type BoardIdentity,
  type CachedOperatorBoard,
} from "@/features/operator-data/last-good-store"
import { getPreviewViewState, type PreviewViewState } from "@/features/operator-data/view-state"
import { getCurrentRelease } from "@/lib/lazy-import"

const BOARD_POLL_INTERVAL_MS = 20_000
const RELEASE = getCurrentRelease()
const boardStore = createLastGoodBoardStore({ release: RELEASE })

export type OperatorRouteContext = {
  track: OperatorTrack
  mode: OperatorMode
  eventId?: string | null
}

type SnapshotMetadataContextValue = {
  bootstrap: OperatorBootstrap | undefined
  isBootstrapLoading: boolean
  bootstrapError: ApiError | null
  refresh: () => void
}

type BoardDataContextValue = {
  board: OperatorBoard | null
  lastGoodBoard: OperatorBoard | null
  viewState: PreviewViewState
  cacheHydration: "pending" | "ready"
  error: ApiError | null
}

const SnapshotMetadataContext = createContext<SnapshotMetadataContextValue | null>(null)
const BoardDataContext = createContext<BoardDataContextValue | null>(null)

const toApiError = (error: unknown): ApiError | null => {
  if (!error) return null
  return error as ApiError
}

const getIdentity = (
  bootstrap: OperatorBootstrap | undefined,
  route: OperatorRouteContext,
): BoardIdentity | null => {
  const eventId = route.eventId ?? bootstrap?.tracks[route.track]?.[route.mode]?.event_id ?? null
  const schemaVersion = bootstrap?.schema_version
  if (!schemaVersion || !eventId) return null
  return {
    schemaVersion,
    release: RELEASE,
    track: route.track,
    mode: route.mode,
    eventId,
  }
}

const supportsBoard = (bootstrap: OperatorBootstrap | undefined, route: OperatorRouteContext): boolean => {
  if (!bootstrap || bootstrap.state === "error") return false
  return Boolean(route.eventId ?? bootstrap.tracks[route.track]?.[route.mode]?.event_id)
}

export function OperatorDataProvider({
  children,
  route,
}: {
  children: ReactNode
  route: OperatorRouteContext
}) {
  const bootstrapQuery = useQuery({
    queryKey: ["operator", "bootstrap"],
    queryFn: ({ signal }) => getOperatorBootstrap(signal),
    refetchInterval: BOARD_POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  })
  const bootstrap = bootstrapQuery.data
  const identity = getIdentity(bootstrap, route)
  const canLoadBoard = supportsBoard(bootstrap, route)
  const [lastGoodEntry, setLastGoodEntry] = useState<CachedOperatorBoard | null>(null)
  const [cacheHydration, setCacheHydration] = useState<"pending" | "ready">("pending")

  useEffect(() => {
    let active = true
    setCacheHydration("pending")
    setLastGoodEntry(null)
    if (!identity) {
      setCacheHydration("ready")
      return () => {
        active = false
      }
    }
    void boardStore.read(identity).then((entry) => {
      if (!active) return
      setLastGoodEntry(entry)
      setCacheHydration("ready")
    })
    return () => {
      active = false
    }
  }, [identity?.schemaVersion, identity?.track, identity?.mode, identity?.eventId])

  const boardQuery = useQuery({
    queryKey: ["operator", "board", route.track, route.mode, identity?.eventId ?? null],
    queryFn: ({ signal }) =>
      getOperatorBoard(
        {
          track: route.track,
          mode: route.mode,
          eventId: identity?.eventId,
        },
        signal,
      ),
    enabled: canLoadBoard && Boolean(identity),
    refetchInterval: BOARD_POLL_INTERVAL_MS,
    placeholderData: keepPreviousData,
  })

  useEffect(() => {
    const board = boardQuery.data
    if (!identity || !board || board.state !== "fresh") return
    const entry: CachedOperatorBoard = {
      identity,
      board,
      savedAt: Date.now(),
      snapshotId: board.source.snapshot_id ?? null,
    }
    setLastGoodEntry((current) =>
      current?.snapshotId === entry.snapshotId && current.savedAt >= entry.savedAt ? current : entry,
    )
    void boardStore.save(entry)
  }, [boardQuery.data, identity])

  const lastGoodBoard = lastGoodEntry?.board ?? null
  const liveBoard = bootstrap?.state === "error" ? undefined : boardQuery.data
  const error = toApiError(bootstrapQuery.error ?? boardQuery.error)
  const viewState = getPreviewViewState({
    bootstrap,
    board: liveBoard,
    hasLastGood: Boolean(lastGoodBoard),
    cacheHydrationPending: cacheHydration === "pending",
    isBoardLoading: boardQuery.isLoading,
    isBoardError: Boolean(error),
  })

  const metadataValue = useMemo<SnapshotMetadataContextValue>(
    () => ({
      bootstrap,
      isBootstrapLoading: bootstrapQuery.isLoading,
      bootstrapError: toApiError(bootstrapQuery.error),
      refresh: () => {
        void bootstrapQuery.refetch()
        void boardQuery.refetch()
      },
    }),
    [bootstrap, bootstrapQuery],
  )
  const boardValue = useMemo<BoardDataContextValue>(
    () => ({
      board: liveBoard ?? (viewState === "stale" ? lastGoodBoard : null),
      lastGoodBoard,
      viewState,
      cacheHydration,
      error,
    }),
    [cacheHydration, error, lastGoodBoard, liveBoard, viewState],
  )

  return (
    <SnapshotMetadataContext.Provider value={metadataValue}>
      <BoardDataContext.Provider value={boardValue}>{children}</BoardDataContext.Provider>
    </SnapshotMetadataContext.Provider>
  )
}

export const useOperatorSnapshotMetadata = (): SnapshotMetadataContextValue => {
  const context = useContext(SnapshotMetadataContext)
  if (!context) throw new Error("useOperatorSnapshotMetadata must be used within OperatorDataProvider")
  return context
}

export const useOperatorBoardData = (): BoardDataContextValue => {
  const context = useContext(BoardDataContext)
  if (!context) throw new Error("useOperatorBoardData must be used within OperatorDataProvider")
  return context
}

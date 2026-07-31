import type { QueryClient } from "@tanstack/react-query"

import { getOperatorBoard, getOperatorBootstrap, type OperatorMode, type OperatorTrack } from "@/features/operator-data/operator-api"

export type PreviewRoute = {
  id: "dashboard" | "lab"
  path: "/preview/dashboard" | "/preview/lab"
  track: OperatorTrack
  mode: OperatorMode
  load: () => Promise<unknown>
}

export const PREVIEW_ROUTE_MANIFEST: readonly PreviewRoute[] = [
  {
    id: "dashboard",
    path: "/preview/dashboard",
    track: "champion",
    mode: "live",
    load: () => import("@/app/operator/operator-app"),
  },
  {
    id: "lab",
    path: "/preview/lab",
    track: "challenger",
    mode: "live",
    load: () => import("@/app/operator/operator-app"),
  },
]

export const findPreviewRoute = (pathname: string): PreviewRoute | undefined =>
  PREVIEW_ROUTE_MANIFEST.find((route) => route.path === pathname)

export const preloadPreviewRoute = (route: PreviewRoute): void => {
  void route.load()
}

export const prefetchPreviewRoute = async (
  queryClient: QueryClient,
  route: PreviewRoute,
): Promise<void> => {
  await queryClient.prefetchQuery({
    queryKey: ["operator", "bootstrap"],
    queryFn: ({ signal }) => getOperatorBootstrap(signal),
  })
  const bootstrap = queryClient.getQueryData<Awaited<ReturnType<typeof getOperatorBootstrap>>>([
    "operator",
    "bootstrap",
  ])
  const eventId = bootstrap?.tracks[route.track]?.[route.mode]?.event_id
  if (!eventId) return
  await queryClient.prefetchQuery({
    queryKey: ["operator", "board", route.track, route.mode, eventId],
    queryFn: ({ signal }) => getOperatorBoard({ track: route.track, mode: route.mode, eventId }, signal),
  })
}

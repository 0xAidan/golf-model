import { Navigate, Route, Routes } from "react-router-dom"

import { OperatorApp } from "@/app/operator/operator-app"
import { OperatorDataProvider, type OperatorRouteContext } from "@/features/operator-data/operator-data-provider"

const PreviewRoute = ({ route }: { route: OperatorRouteContext }) => (
  <OperatorDataProvider route={route}>
    <OperatorApp />
  </OperatorDataProvider>
)

export function OperatorRoutes() {
  return (
    <Routes>
      <Route path="/preview" element={<Navigate to="/preview/dashboard" replace />} />
      <Route
        path="/preview/dashboard"
        element={<PreviewRoute route={{ track: "champion", mode: "live" }} />}
      />
      <Route
        path="/preview/lab"
        element={<PreviewRoute route={{ track: "challenger", mode: "live" }} />}
      />
      <Route path="/preview/*" element={<Navigate to="/preview/dashboard" replace />} />
    </Routes>
  )
}

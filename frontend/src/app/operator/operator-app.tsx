import { OperatorShell } from "@/app/operator/operator-shell"
import { DashboardPreviewPage } from "@/features/dashboard/dashboard-preview-page"

export function OperatorApp({ track }: { track: "champion" | "challenger" }) {
  return <OperatorShell><DashboardPreviewPage track={track} /></OperatorShell>
}

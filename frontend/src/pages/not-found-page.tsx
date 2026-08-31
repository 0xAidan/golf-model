import { Link } from "react-router-dom"

import { PageHeader } from "@/components/ui/page-header"

export const NotFoundPage = () => (
  <div className="page-shell--route px-5 py-6" data-testid="not-found-page">
    <PageHeader
      eyebrow="404"
      title="That page is not here"
      description="The URL does not match a Dashboard, Lab, Players, Results, or System route."
    />
    <p className="mt-4 text-sm text-[var(--text-muted)]">
      Go back to the{" "}
      <Link to="/" className="link-subtle font-semibold text-[var(--text)]">
        Dashboard
      </Link>{" "}
      or open Results to grade a completed event.
    </p>
  </div>
)

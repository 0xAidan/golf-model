import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

export const ModelCommandSection = ({
  id,
  title,
  description,
  action,
  children,
  variant = "default",
  testId,
}: {
  id: string
  title: string
  description?: string
  action?: ReactNode
  children: ReactNode
  variant?: "default" | "picks"
  testId?: string
}) => (
  <section
    id={id}
    className={cn(
      "model-command-section",
      variant === "picks" && "model-command-section--picks",
    )}
    data-testid={testId ?? `model-section-${id}`}
    aria-labelledby={`${id}-heading`}
  >
    <div className="model-command-section__header">
      <div>
        <h2 id={`${id}-heading`} className="model-command-section__title">
          {title}
        </h2>
        {description ? (
          <p className="model-command-section__desc">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
    <div className="model-command-section__body">{children}</div>
  </section>
)

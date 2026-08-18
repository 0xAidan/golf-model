import type { Preview } from "@storybook/react"

import "../src/index.css"

const preview: Preview = {
  parameters: {
    layout: "fullscreen",
    backgrounds: {
      default: "dark",
      values: [{ name: "dark", value: "#090b0d" }],
    },
  },
  decorators: [
    (Story) => {
      document.documentElement.classList.add("dark")
      return (
        <div className="monitor-lane p-4" style={{ minHeight: 200 }}>
          <Story />
        </div>
      )
    },
  ],
}

export default preview

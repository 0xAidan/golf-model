import type { Preview } from "@storybook/react"

import "../src/index.css"

const preview: Preview = {
  parameters: {
    layout: "fullscreen",
    backgrounds: {
      default: "dark",
      values: [
        { name: "dark", value: "#0a0c0f" },
        { name: "light", value: "#f4f5f7" },
      ],
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

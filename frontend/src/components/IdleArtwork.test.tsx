import { render } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { IdleArtwork } from "./IdleArtwork"

describe("IdleArtwork", () => {
  it("links each preview to its own accessible title", () => {
    const { container } = render(
      <>
        <IdleArtwork />
        <IdleArtwork />
      </>,
    )
    const previews = [...container.querySelectorAll("svg")]
    const titleIds = previews.map((preview) =>
      preview.querySelector("title")?.id,
    )

    expect(new Set(titleIds).size).toBe(2)
    previews.forEach((preview, index) => {
      expect(preview).toHaveAttribute("aria-labelledby", titleIds[index])
    })
  })
})
